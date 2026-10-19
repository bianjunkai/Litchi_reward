import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from database import connect, init_db
from main import create_app, today

PIN = '863925'


@pytest.fixture
def family(tmp_path):
    path = tmp_path / 'family.db'
    client = TestClient(create_app(path,parent_pin=PIN))
    session = client.post('/api/auth/parent',json={'pin':PIN}).json()
    return client, {'Authorization':f"Bearer {session['token']}"}, path


def post(client, headers, url, payload=None):
    return client.post(url,headers=headers,**({} if payload is None else {'json':payload}))


def balance(client, code):
    return next(a['balance'] for a in client.get('/api/dashboard/1').json()['assets'] if a['code']==code)


def fund(client, headers, code='coupon', amount=1):
    response = post(client,headers,'/api/parent/adjust',{'asset_code':code,'delta':amount,'reason':'测试补发'})
    assert response.status_code==200
    return response.json()['operation_id']


def assert_balanced(path):
    with connect(path) as db:
        rows = db.execute('''SELECT ca.balance,COALESCE(SUM(l.delta),0) AS changes FROM child_assets ca
            LEFT JOIN ledger l ON l.child_id=ca.child_id AND l.asset_type_id=ca.asset_type_id
            GROUP BY ca.child_id,ca.asset_type_id''').fetchall()
        assert all(r['balance']==r['changes'] and r['balance']>=0 for r in rows)
        assert not db.execute('PRAGMA foreign_key_check').fetchone()


def test_new_family_has_no_demo_money(family):
    client, _, path = family
    assert client.get('/api/health').json()['status']=='ok'
    dashboard = client.get('/api/dashboard/1').json()
    assert len(dashboard['assets'])==5
    assert all(a['balance']==0 for a in dashboard['assets'])
    assert not next(a for a in dashboard['assets'] if a['code']=='gold_star')['active']
    assert_balanced(path)


def test_first_time_setup_and_no_default_pin(tmp_path):
    client = TestClient(create_app(tmp_path/'setup.db',parent_pin=''))
    assert client.get('/api/auth/status').json()['setup_required']
    assert client.post('/api/auth/setup',json={'pin':'1234'}).status_code==422
    result = client.post('/api/auth/setup',json={'pin':PIN})
    assert result.status_code==200
    assert not client.get('/api/auth/status').json()['setup_required']
    assert client.post('/api/auth/setup',json={'pin':'983456'}).status_code==409


def test_auth_requires_session_and_logout_revokes(family):
    client, headers, _ = family
    assert client.post('/api/tasks/1/claim',headers={'X-Parent-Pin':PIN}).status_code==401
    assert post(client,headers,'/api/auth/logout').status_code==200
    assert client.get('/api/parent/summary',headers=headers).status_code==401


def test_login_failures_persist_and_expire(family):
    client, _, _ = family
    with patch('main.time.time',return_value=1000):
        for _ in range(5):
            assert client.post('/api/auth/parent',json={'pin':'bad'}).status_code==401
        assert client.post('/api/auth/parent',json={'pin':PIN}).status_code==429
    with patch('main.time.time',return_value=1301):
        assert client.post('/api/auth/parent',json={'pin':PIN}).status_code==200


def test_change_pin_and_session_expiry(family):
    client, headers, path = family
    assert post(client,headers,'/api/parent/pin',{'pin':'564738'}).status_code==200
    assert client.get('/api/parent/summary',headers=headers).status_code==401
    assert client.post('/api/auth/parent',json={'pin':PIN}).status_code==401
    session = client.post('/api/auth/parent',json={'pin':'564738'}).json()
    with connect(path) as db:
        assert '564738' not in db.execute('SELECT pin_hash FROM parent_auth').fetchone()[0]
        db.execute('UPDATE sessions SET expires_at=0')
    assert client.get('/api/parent/summary',headers={'Authorization':f"Bearer {session['token']}"}).status_code==401


def test_claim_is_daily_and_undo_allows_reclaim(family):
    client, headers, path = family
    first = post(client,headers,'/api/tasks/1/claim')
    assert first.status_code==200
    assert post(client,headers,'/api/tasks/1/claim').status_code==409
    op = first.json()['operation_id']
    assert post(client,headers,f'/api/parent/operations/{op}/reverse').status_code==200
    assert balance(client,'study_star')==0
    assert post(client,headers,'/api/tasks/1/claim').status_code==200
    assert post(client,headers,f'/api/parent/operations/{op}/reverse').status_code==409
    assert_balanced(path)


def test_family_day_and_actual_claim_boundary(family):
    client, headers, path = family
    with patch('main.datetime') as clock:
        clock.now.return_value = datetime(2026,10,18,15,59,tzinfo=timezone.utc)
        assert today()=='2026-10-18'
        assert post(client,headers,'/api/tasks/1/claim').status_code==200
        clock.now.return_value = datetime(2026,10,18,16,0,tzinfo=timezone.utc)
        assert today()=='2026-10-19'
        assert post(client,headers,'/api/tasks/1/claim').status_code==200
    assert balance(client,'study_star')==2
    assert_balanced(path)


@pytest.mark.parametrize('url,payload',[('/api/redemptions',{'child_id':999,'product_id':1}),
    ('/api/tasks/1/claim?child_id=999',None),('/api/parent/adjust',{'child_id':999,'asset_code':'coupon','delta':1,'reason':'纠错'})])
def test_unknown_child_returns_not_found(family,url,payload):
    client, headers, _ = family
    assert post(client,headers,url,payload).status_code==404


def test_full_reward_chain_and_reverse_dependencies(family):
    client, headers, path = family
    fund(client,headers,'study_star',5)
    badge_op = post(client,headers,'/api/parent/conversions/stars',{'badge_id':2,'color':'#d4af37'}).json()['operation_id']
    assert balance(client,'study_star')==0
    badge = next(b for b in client.get('/api/badges').json() if b['code']=='life')
    assert (badge['earned_count'],badge['available_count'])==(1,1)
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    sport_task = {'name':'运动阶段目标','badge_id':1,'amount':4,'badge_color':'#aab5c4'}
    assert client.put('/api/parent/tasks/4',headers=headers,json=sport_task).status_code==200
    assert post(client,headers,'/api/tasks/4/claim').status_code==200
    coupon_op = post(client,headers,'/api/parent/conversions/coupon',{}).json()['operation_id']
    badge = next(b for b in client.get('/api/badges').json() if b['code']=='life')
    assert (badge['earned_count'],badge['available_count'])==(1,0)
    assert post(client,headers,f'/api/parent/operations/{badge_op}/reverse').status_code==409
    requested = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    assert balance(client,'coupon')==1  # Application never spends the coupon.
    approved = post(client,headers,f'/api/parent/redemptions/{requested}/approve',{'actual_amount_fen':3990}).json()['operation_id']
    assert balance(client,'coupon')==0
    assert post(client,headers,f'/api/parent/operations/{coupon_op}/reverse').status_code==409
    assert post(client,headers,f'/api/parent/operations/{approved}/reverse').status_code==200
    assert post(client,headers,f'/api/parent/operations/{coupon_op}/reverse').status_code==200
    assert post(client,headers,f'/api/parent/operations/{badge_op}/reverse').status_code==200
    assert balance(client,'study_star')==5
    assert balance(client,'coupon')==0
    history = client.get('/api/badges/history').json()
    assert next(b for b in history if b['code']=='life')['reversed_at']
    assert all(b['spent_operation_id'] is None for b in history if b['code']=='sports')
    assert_balanced(path)


def test_partial_conversion_failure_rolls_back(family):
    client, headers, path = family
    fund(client,headers,'study_star',2)
    before = client.get('/api/parent/operations',headers=headers).json()
    assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':2}).status_code==409
    assert balance(client,'study_star')==2
    assert client.get('/api/parent/operations',headers=headers).json()==before
    assert_balanced(path)


def test_sport_task_grants_badge_once(family):
    client, headers, path = family
    assert post(client,headers,'/api/tasks/4/claim').status_code==200
    assert post(client,headers,'/api/tasks/4/claim').status_code==409
    badge = next(b for b in client.get('/api/badges').json() if b['code']=='sports')
    assert badge['earned_count']==1
    assert_balanced(path)


def test_concurrent_same_approval_only_spends_once(family):
    client, headers, path = family
    fund(client,headers)
    item = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: post(client,headers,f'/api/parent/redemptions/{item}/approve',{'actual_amount_fen':3990}).status_code,range(8)))
    assert results.count(200)==1
    assert results.count(409)==7
    assert balance(client,'coupon')==0
    assert_balanced(path)


def test_concurrent_different_approvals_cannot_overspend(family):
    client, headers, path = family
    fund(client,headers)
    ids = [client.post('/api/redemptions',json={'product_id':p}).json()['id'] for p in (1,2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: post(client,headers,f'/api/parent/redemptions/{i}/approve',{'actual_amount_fen':3990}).status_code,ids))
    assert sorted(results)==[200,409]
    assert balance(client,'coupon')==0
    assert_balanced(path)


def test_concurrent_adjustments_never_make_negative_balance(family):
    client, headers, path = family
    fund(client,headers)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: post(client,headers,'/api/parent/adjust',{'asset_code':'coupon','delta':-1,'reason':'扣除'}).status_code,range(4)))
    assert results.count(200)==1 and results.count(409)==3
    assert_balanced(path)


def test_redemption_is_deduplicated_and_price_snapshot_preserved(family):
    client, headers, _ = family
    fund(client,headers)
    first = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    assert client.post('/api/redemptions',json={'product_id':1}).json()['id']==first
    product = client.get('/api/parent/products',headers=headers).json()[0]
    product.update(price=5,name='新版商品',active=False,cash_price_fen=19950)
    assert client.put('/api/parent/products/1',headers=headers,json=product).status_code==200
    assert post(client,headers,f'/api/parent/redemptions/{first}/approve',{'actual_amount_fen':3990}).status_code==200
    record = client.get('/api/parent/redemptions',headers=headers).json()[0]
    assert record['price']==1 and record['product_name']=='木马王国门票'


def test_app_instances_use_their_own_database(family,tmp_path):
    a, headers, _ = family
    fund(a,headers,amount=8)
    b = TestClient(create_app(tmp_path/'other.db',parent_pin=PIN))
    assert balance(a,'coupon')==8
    assert balance(b,'coupon')==0


def test_rules_tasks_and_badges_are_editable(family):
    client, headers, _ = family
    rule = {'badge_ratio':3,'badges_per_coupon':2,'family_timezone':'Asia/Shanghai'}
    assert client.put('/api/parent/rules',headers=headers,json=rule).status_code==422
    rule.update(badge_ratio=5,badges_per_coupon=5,family_timezone='UTC')
    assert client.put('/api/parent/rules',headers=headers,json=rule).status_code==200
    assert client.get('/api/dashboard/1').json()['progress']['target']==5
    result = post(client,headers,'/api/parent/tasks',{'name':'游泳','badge_id':1,'amount':1}).json()
    assert post(client,headers,f"/api/tasks/{result['id']}/claim").status_code==200
    item = client.get('/api/parent/tasks',headers=headers).json()[-1]
    item['active']=False
    assert client.put(f"/api/parent/tasks/{item['id']}",headers=headers,json=item).status_code==200
    assert all(t['id']!=item['id'] for t in client.get('/api/tasks').json())
    badge = {'code':'courage','name':'勇气徽章','icon':'🌟','color':'#d4af37','active':True}
    assert post(client,headers,'/api/parent/badges',badge).status_code==422
    badge.update(code='fire',name='预留徽章 A',active=True)
    assert client.put('/api/parent/badges/3',headers=headers,json=badge).status_code==200
    badge['active']=False
    assert client.put('/api/parent/badges/3',headers=headers,json=badge).status_code==200


def test_backup_roundtrip_preserves_auth_and_history(family):
    client, headers, path = family
    fund(client,headers,'study_star',25)
    for _ in range(5):
        assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':2}).status_code==200
    post(client,headers,'/api/parent/conversions/coupon',{})
    exported = client.get('/api/parent/backup',headers=headers).json()
    assert 'sessions' not in exported['tables'] and 'parent_auth' not in exported['tables']
    fund(client,headers,amount=9)
    result = post(client,headers,'/api/parent/restore',exported)
    assert result.status_code==200,result.text
    assert balance(client,'coupon')==1
    assert client.get('/api/parent/summary',headers=headers).status_code==200
    saved = path.parent/'backups'/result.json()['safety_backup']
    assert saved.is_file()
    assert_balanced(path)


@pytest.mark.parametrize('damage',['balance','foreign_key','missing_table','columns','rules','negative','price'])
def test_invalid_restore_is_rejected_without_changing_data(family,damage):
    client, headers, path = family
    fund(client,headers,amount=3)
    before = client.get('/api/parent/backup',headers=headers).json()
    broken = copy.deepcopy(before)
    if damage=='balance': broken['tables']['child_assets'][0]['balance']=99
    if damage=='foreign_key': broken['tables']['ledger'][0]['child_id']=999
    if damage=='missing_table': del broken['tables']['ledger']
    if damage=='columns': broken['tables']['products'][0]['invented']='x'
    if damage=='rules': broken['rules']['family_timezone']='Nowhere/Invalid'
    if damage=='negative': broken['tables']['child_assets'][0]['balance']=-1
    if damage=='price': broken['tables']['products'][0]['price']=-1
    assert post(client,headers,'/api/parent/restore',broken).status_code==422
    after = client.get('/api/parent/backup',headers=headers).json()
    assert before['tables']==after['tables']
    assert_balanced(path)


def test_upgrade_old_balance_adds_opening_ledger_once(tmp_path):
    path = tmp_path/'old.db'
    db = sqlite3.connect(path)
    db.executescript('''CREATE TABLE children(id INTEGER PRIMARY KEY,name TEXT NOT NULL,avatar TEXT NOT NULL DEFAULT '🍄');
        CREATE TABLE asset_types(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,icon TEXT,color TEXT,kind TEXT DEFAULT 'currency',active INTEGER DEFAULT 1);
        CREATE TABLE child_assets(child_id INTEGER,asset_type_id INTEGER,balance INTEGER DEFAULT 0,PRIMARY KEY(child_id,asset_type_id));
        CREATE TABLE ledger(id INTEGER PRIMARY KEY,child_id INTEGER,asset_type_id INTEGER,delta INTEGER,reason TEXT,reference_type TEXT DEFAULT '',reference_id INTEGER,created_at TEXT);
        INSERT INTO children(id,name) VALUES (1,'旧账户');
        INSERT INTO asset_types(id,code,name,icon,color) VALUES (1,'study_star','学习','⭐','#ffffff');
        INSERT INTO child_assets VALUES (1,1,3);''')
    db.close()
    init_db(path)
    init_db(path)
    with connect(path) as db:
        assert db.execute('SELECT balance FROM child_assets').fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM ledger WHERE reference_type='opening_balance'").fetchone()[0]==1
    assert_balanced(path)
