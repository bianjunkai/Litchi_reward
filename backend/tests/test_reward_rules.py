import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from database import connect, init_db, utc_now
from main import create_app
from reward_rules import BADGE_COLORS
from test_api import family, post, fund, balance, assert_balanced


def grant_badges(client, headers, badge_id, amount, color=None):
    task = post(client,headers,'/api/parent/tasks',{
        'name':'约定的阶段目标','badge_id':badge_id,'amount':amount,'badge_color':color,
    })
    assert task.status_code==200,task.text
    response = post(client,headers,f"/api/tasks/{task.json()['id']}/claim")
    assert response.status_code==200,response.text
    return response.json()['operation_id']


def set_badge_active(client, headers, badge_id, active):
    badge = next(b for b in client.get('/api/parent/badges',headers=headers).json() if b['id']==badge_id)
    badge['active']=active
    assert client.put(f'/api/parent/badges/{badge_id}',headers=headers,json=badge).status_code==200


def test_twenty_five_mixed_stars_become_five_life_badges_and_one_coupon(family):
    client, headers, path = family
    fund(client,headers,'study_star',10)
    fund(client,headers,'tidy_star',8)
    fund(client,headers,'meal_star',7)
    for index,color in enumerate(BADGE_COLORS):
        assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':2,'color':color}).status_code==200
        if index<4:
            assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    result = post(client,headers,'/api/parent/conversions/coupon',{})
    assert result.status_code==200
    assert result.json()['badges_consumed']==5
    assert result.json()['coupon_value_fen']==3990
    dashboard = client.get('/api/dashboard/1').json()
    assert dashboard['progress']['total_stars']==0
    assert dashboard['coupons']['balance']==1 and dashboard['coupons']['total_value_fen']==3990
    badge = next(b for b in dashboard['badges'] if b['code']=='life')
    assert (badge['earned_count'],badge['unspent_count'],badge['available_count'])==(5,0,0)
    assert {b['color'] for b in client.get('/api/badges/history').json()}==set(BADGE_COLORS)
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    assert_balanced(path)


@pytest.mark.parametrize('badge_id',[1,3,4])
def test_stars_cannot_buy_sports_or_reserved_badges(family,badge_id):
    client, headers, path = family
    if badge_id!=1:
        set_badge_active(client,headers,badge_id,True)
    fund(client,headers,'study_star',25)
    assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':badge_id}).status_code==422
    assert balance(client,'study_star')==25
    assert not client.get('/api/badges/history').json()
    assert_balanced(path)


def test_mixed_badges_count_only_when_enabled_and_each_is_spent_once(family):
    client, headers, path = family
    set_badge_active(client,headers,3,True)
    set_badge_active(client,headers,4,True)
    grant_badges(client,headers,1,2,'#4eb478')
    grant_badges(client,headers,3,1,'#aab5c4')
    grant_badges(client,headers,4,1,'#d4af37')
    fund(client,headers,'study_star',5)
    assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':2,'color':'#e55353'}).status_code==200
    set_badge_active(client,headers,3,False)
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    badge = next(b for b in client.get('/api/badges').json() if b['code']=='fire')
    assert badge['earned_count']==1 and badge['unspent_count']==1 and badge['available_count']==0
    set_badge_active(client,headers,3,True)
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==200
    history = client.get('/api/badges/history').json()
    assert len(history)==5 and all(b['spent_operation_id'] is not None for b in history)
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    assert_balanced(path)


def test_daily_star_limits_survive_duplicate_tasks_and_concurrent_claims(family):
    client, headers, path = family
    extra = post(client,headers,'/api/parent/tasks',{'name':'认真读书','asset_code':'study_star'}).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: post(client,headers,f'/api/tasks/{i}/claim').status_code,[1,extra]))
    assert sorted(results)==[200,409]
    assert balance(client,'study_star')==1
    assert all(t['claimed_today'] for t in client.get('/api/tasks').json() if t['asset_code']=='study_star' and not t['badge_id'])
    assert post(client,headers,'/api/parent/tasks',{'name':'多发代币','asset_code':'study_star','amount':2}).status_code==422
    assert post(client,headers,'/api/parent/tasks',{'name':'金色任务','asset_code':'gold_star'}).status_code==422
    assert post(client,headers,'/api/parent/tasks',{'name':'直接发生活徽章','badge_id':2}).status_code==422
    assert_balanced(path)


def test_reserved_badges_start_disabled_and_cannot_be_awarded(family):
    client, headers, _ = family
    result = post(client,headers,'/api/parent/tasks',{'name':'预留任务','badge_id':3}).json()['id']
    assert post(client,headers,f'/api/tasks/{result}/claim').status_code==409
    assert not any(t['id']==result for t in client.get('/api/tasks').json())


@pytest.mark.parametrize('color',BADGE_COLORS)
def test_all_badge_colors_are_cosmetic_and_do_not_change_cost(family,color):
    client, headers, _ = family
    fund(client,headers,'study_star',5)
    assert post(client,headers,'/api/parent/conversions/stars',{'badge_id':2,'color':color}).status_code==200
    assert balance(client,'study_star')==0
    grant_badges(client,headers,1,1,color)
    assert all(b['color']==color for b in client.get('/api/badges/history').json())


@pytest.mark.parametrize('count,actual,top_up,forfeited',[
    (1,3990,0,0),(1,5000,1010,0),(1,3000,0,990),(5,19950,0,0),
    (5,20000,50,0),(5,10000,0,9950),(1,0,0,3990),
])
def test_coupon_settlement_records_exact_fen_and_leaves_no_change_credit(family,count,actual,top_up,forfeited):
    client, headers, path = family
    fund(client,headers,amount=8)
    item = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    assert balance(client,'coupon')==8
    response = post(client,headers,f'/api/parent/redemptions/{item}/approve',{
        'actual_amount_fen':actual,'coupon_count':count,'approve_top_up':bool(top_up),'note':'双方确认的消费',
    })
    assert response.status_code==200,response.text
    assert balance(client,'coupon')==8-count
    record = client.get('/api/parent/redemptions',headers=headers).json()[0]
    assert record['coupon_value_fen']==3990 and record['coupons_used']==count
    assert record['actual_amount_fen']==actual and record['parent_top_up_fen']==top_up and record['forfeited_fen']==forfeited
    assert record['settlement_note']=='双方确认的消费'
    assert all(a['balance']==0 for a in client.get('/api/dashboard/1').json()['assets'] if a['code']!='coupon')
    assert_balanced(path)


def test_parent_must_explicitly_approve_top_up_and_enter_actual_amount(family):
    client, headers, path = family
    fund(client,headers)
    item = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    url = f'/api/parent/redemptions/{item}/approve'
    assert post(client,headers,url).status_code==422
    assert post(client,headers,url,{'actual_amount_fen':5000}).status_code==409
    assert post(client,headers,url,{'actual_amount_fen':39.9}).status_code==422
    assert balance(client,'coupon')==1
    assert client.get('/api/parent/redemptions',headers=headers).json()[0]['status']=='pending'
    assert post(client,headers,f'/api/parent/redemptions/{item}/reject').status_code==200
    assert balance(client,'coupon')==1
    assert_balanced(path)


@pytest.mark.parametrize('count',[0,6,99,-1])
def test_single_use_limit_cannot_be_bypassed_even_with_large_balance(family,count):
    client, headers, path = family
    fund(client,headers,amount=99)
    item = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    assert post(client,headers,f'/api/parent/redemptions/{item}/approve',{'coupon_count':count,'actual_amount_fen':30000,'approve_top_up':True}).status_code==422
    assert balance(client,'coupon')==99
    assert post(client,headers,'/api/parent/products',{'name':'超额商品','price':6}).status_code==422
    assert_balanced(path)


def test_concurrent_badge_to_coupon_does_not_consume_same_five_twice(family):
    client, headers, path = family
    grant_badges(client,headers,1,5)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: post(client,headers,'/api/parent/conversions/coupon',{}).status_code,range(4)))
    assert sorted(results)==[200,409,409,409]
    assert balance(client,'coupon')==1
    assert_balanced(path)


def test_migration_preserves_historical_wrong_ratio_transactions(family):
    client, headers, path = family
    grant_badges(client,headers,1,1)
    with connect(path) as db:
        old_coupon = db.execute("INSERT INTO operations(child_id,kind,reason,created_at,rule_version) VALUES (1,'badges_to_coupon','旧版 1 枚换券',?,'legacy')",(utc_now(),)).lastrowid
        db.execute('UPDATE child_badges SET spent_operation_id=?',(old_coupon,))
        asset = db.execute("SELECT id FROM asset_types WHERE code='coupon'").fetchone()[0]
        db.execute("INSERT INTO ledger(child_id,asset_type_id,delta,reason,created_at,operation_id) VALUES (1,?,1,'旧版换券',?,?)",(asset,utc_now(),old_coupon))
        spent = db.execute("INSERT INTO operations(child_id,kind,reason,created_at,rule_version) VALUES (1,'redemption','旧消费',?,'legacy')",(utc_now(),)).lastrowid
        db.execute("INSERT INTO ledger(child_id,asset_type_id,delta,reason,created_at,operation_id) VALUES (1,?,-1,'旧版消费',?,?)",(asset,utc_now(),spent))
        db.execute("INSERT INTO redemptions(child_id,product_id,status,requested_at,operation_id,product_name,price) VALUES (1,1,'approved',?,?,'旧消费',1)",(utc_now(),spent))
        db.execute("DELETE FROM settings WHERE key='family_rules_version'")
        db.execute("UPDATE settings SET value='1' WHERE key IN ('badge_ratio','badges_per_coupon')")
        db.execute("UPDATE badges SET threshold=1 WHERE code='life'")
        before = {t:[tuple(r) for r in db.execute(f'SELECT * FROM {t}')] for t in ['child_assets','child_badges','redemptions','ledger','operations']}
    init_db(path)
    init_db(path)
    with connect(path) as db:
        after = {t:[tuple(r) for r in db.execute(f'SELECT * FROM {t}')] for t in before}
        assert before==after
        assert dict(db.execute("SELECT key,value FROM settings WHERE key IN ('badge_ratio','badges_per_coupon')"))=={'badge_ratio':'5','badges_per_coupon':'5'}
        assert db.execute("SELECT COUNT(*) FROM audit_logs WHERE action='family_rules_corrected'").fetchone()[0]==2  # Initial setup + simulated old-version migration.
    assert path.with_name(path.name+'.pre-family-v1.db').is_file()
    assert_balanced(path)


def test_legacy_backup_import_corrects_only_future_rules(family):
    client, headers, path = family
    grant_badges(client,headers,1,1)
    backup = client.get('/api/parent/backup',headers=headers).json()
    backup['version']=1
    backup['rules'].update(badge_ratio='1',badges_per_coupon='1')
    new_columns = {'tasks':['badge_color'],'products':['cash_price_fen'],'operations':['rule_version'],
        'redemptions':['coupon_value_fen','coupons_used','actual_amount_fen','parent_top_up_fen','forfeited_fen','quoted_amount_fen','settlement_note','rule_version']}
    for table,columns in new_columns.items():
        for row in backup['tables'][table]:
            for column in columns: row.pop(column,None)
    result = post(client,headers,'/api/parent/restore',backup)
    assert result.status_code==200,result.text
    assert client.get('/api/parent/rules',headers=headers).json()['badges_per_coupon']==5
    assert client.get('/api/badges/history').json()[0]['spent_operation_id'] is None
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==409
    assert_balanced(path)


def test_settlement_backup_rejects_tampered_financial_math(family):
    client, headers, _ = family
    fund(client,headers)
    item = client.post('/api/redemptions',json={'product_id':1}).json()['id']
    assert post(client,headers,f'/api/parent/redemptions/{item}/approve',{'actual_amount_fen':3000}).status_code==200
    backup = client.get('/api/parent/backup',headers=headers).json()
    backup['tables']['redemptions'][0]['forfeited_fen']=0
    assert post(client,headers,'/api/parent/restore',backup).status_code==422


@pytest.mark.parametrize('damage',['ratio','gold','fractional_balance','fractional_price'])
def test_backup_cannot_restore_invalid_future_rules_or_fractional_assets(family,damage):
    client, headers, _ = family
    backup = client.get('/api/parent/backup',headers=headers).json()
    if damage=='ratio':
        backup['rules']['badges_per_coupon']='1'
    if damage=='gold':
        next(a for a in backup['tables']['asset_types'] if a['code']=='gold_star')['active']=1
    if damage=='fractional_balance':
        backup['tables']['child_assets'][0]['balance']=0.5
    if damage=='fractional_price':
        backup['tables']['products'][0]['price']=1.5
    assert post(client,headers,'/api/parent/restore',backup).status_code==422
