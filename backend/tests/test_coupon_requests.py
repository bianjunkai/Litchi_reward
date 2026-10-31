import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from database import connect, init_db
from reward_rules import BADGE_COLORS
from test_api import family, post, fund, balance, assert_balanced
from test_reward_rules import grant_badges


def request(client, selections=None):
    return client.post('/api/coupon-requests',json={'selections':selections or [{'badge_id':1,'color':'#4eb478','count':5}]})


def test_child_request_does_not_spend_and_parent_approves_exact_sports_badges(family):
    client,headers,path = family
    fund(client,headers,'study_star',5)
    post(client,headers,'/api/parent/conversions/stars',{'badge_id':2})  # Older life badge must not be consumed instead.
    grant_badges(client,headers,1,5,'#4eb478')
    result = request(client)
    assert result.status_code==200,result.text
    rid = result.json()['id']
    assert balance(client,'coupon')==0
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==6
    assert client.post(f'/api/parent/coupon-requests/{rid}/approve').status_code==401
    assert client.get('/api/parent/coupon-requests').status_code==401
    assert client.get('/api/parent/summary',headers=headers).json()['pending_coupon_requests']==1
    approved = post(client,headers,f'/api/parent/coupon-requests/{rid}/approve')
    assert approved.status_code==200,approved.text
    badges = {b['code']:b for b in client.get('/api/badges').json()}
    assert badges['sports']['available_count']==0 and badges['sports']['earned_count']==5
    assert badges['sports']['colors']==[{'color':'#4eb478','count':5,'available_count':0}]
    assert badges['life']['available_count']==1 and balance(client,'coupon')==1
    assert client.get('/api/coupon-requests').json()['items'][0]['status']=='approved'
    assert len(client.get('/api/backpack/badges?badge_id=1&status=spent').json()['items'])==5
    op = approved.json()['operation_id']
    assert post(client,headers,f'/api/parent/operations/{op}/reverse').status_code==200
    assert balance(client,'coupon')==0
    assert client.get('/api/coupon-requests').json()['items'][0]['status']=='reversed'
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==6
    assert_balanced(path)


def test_mixed_colors_rejection_and_concurrent_approval_are_atomic(family):
    client,headers,path = family
    grant_badges(client,headers,1,3,'#4eb478')
    grant_badges(client,headers,1,2,'#d4af37')
    choices = [{'badge_id':1,'color':'#4eb478','count':3},{'badge_id':1,'color':'#d4af37','count':2}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(client,choices),range(2)))
    assert all(response.status_code==200 for response in responses)
    assert len({response.json()['id'] for response in responses})==1
    rid = responses[0].json()['id']
    assert post(client,headers,f'/api/parent/coupon-requests/{rid}/reject').status_code==200
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==5
    rid = request(client,choices).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(client,headers,f'/api/parent/coupon-requests/{rid}/approve').status_code,range(2)))
    assert sorted(results)==[200,409] and balance(client,'coupon')==1
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==0
    assert_balanced(path)


def test_stale_selected_badges_cannot_issue_a_second_coupon(family):
    client,headers,path = family
    grant_badges(client,headers,1,5,'#4eb478')
    rid = request(client).json()['id']
    assert post(client,headers,'/api/parent/conversions/coupon',{}).status_code==200
    before = client.get('/api/parent/backup',headers=headers).json()['tables']
    assert post(client,headers,f'/api/parent/coupon-requests/{rid}/approve').status_code==409
    assert client.get('/api/parent/backup',headers=headers).json()['tables']==before
    item = client.get('/api/coupon-requests').json()['items'][0]
    assert item['status']=='pending' and not item['can_approve'] and balance(client,'coupon')==1
    assert_balanced(path)


@pytest.mark.parametrize('selections',[
    [{'badge_id':1,'color':'#4eb478','count':4}],
    [{'badge_id':1,'color':'#4eb478','count':2},{'badge_id':1,'color':'#4eb478','count':3}],
    [{'badge_id':1,'color':'#4eb478','count':5.0}],
    [{'badge_id':1,'color':'invalid','count':5}],
])
def test_invalid_coupon_choices_do_not_create_requests(family,selections):
    client,headers,path = family
    grant_badges(client,headers,1,5,'#4eb478')
    assert request(client,selections).status_code==422
    assert client.get('/api/coupon-requests').json()['total']==0
    assert_balanced(path)


def test_requests_cannot_use_another_child_or_inactive_badges(family):
    client,headers,path = family
    grant_badges(client,headers,1,5,'#4eb478')
    with connect(path) as db:
        db.execute("INSERT INTO children(id,name) VALUES (2,'二宝')")
        db.execute('INSERT INTO child_assets SELECT 2,id,0 FROM asset_types')
    assert client.post('/api/coupon-requests',json={'child_id':2,'selections':[{'badge_id':1,'color':'#4eb478','count':5}]}).status_code==409
    with connect(path) as db:
        db.execute('UPDATE badges SET active=0 WHERE id=1')
    assert request(client).status_code==409
    assert client.get('/api/coupon-requests').json()['total']==0


@pytest.mark.parametrize('color',BADGE_COLORS)
def test_parent_can_choose_badge_color_at_award_time_without_editing_task(family,color):
    client,headers,path = family
    assert post(client,headers,'/api/tasks/4/claim',{'color':color}).status_code==200
    entry = client.get('/api/backpack/badges').json()['items'][0]
    assert entry['color']==color and entry['code']=='sports'
    task = next(t for t in client.get('/api/parent/tasks',headers=headers).json() if t['id']==4)
    assert task['badge_color'] is None
    assert post(client,headers,'/api/tasks/4/claim',{'color':color}).status_code==409
    assert_balanced(path)


def test_invalid_award_color_never_claims_the_task(family):
    client,headers,_ = family
    assert post(client,headers,'/api/tasks/4/claim',{'color':'#ffffff'}).status_code==422
    assert not next(t for t in client.get('/api/tasks').json() if t['id']==4)['claimed_today']


def test_coupon_request_backups_roundtrip_and_old_backups_remain_compatible(family):
    client,headers,path = family
    grant_badges(client,headers,1,5,'#4eb478')
    rid = request(client).json()['id']
    snapshot = client.get('/api/parent/backup',headers=headers).json()
    assert snapshot['version']==3
    assert post(client,headers,f'/api/parent/coupon-requests/{rid}/approve').status_code==200
    approved = client.get('/api/parent/backup',headers=headers).json()
    assert post(client,headers,'/api/parent/restore',approved).status_code==200
    bad = copy.deepcopy(snapshot)
    bad['tables']['coupon_request_badges'].pop()
    assert post(client,headers,'/api/parent/restore',bad).status_code==422
    assert post(client,headers,'/api/parent/restore',snapshot).status_code==200
    assert balance(client,'coupon')==0 and client.get('/api/coupon-requests').json()['pending_count']==1
    old = copy.deepcopy(snapshot); old['version']=2
    del old['tables']['coupon_requests']; del old['tables']['coupon_request_badges']
    assert post(client,headers,'/api/parent/restore',old).status_code==200
    assert client.get('/api/coupon-requests').json()['total']==0
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==5
    assert_balanced(path)


def test_upgrade_preserves_existing_assets_and_creates_safety_copy(family):
    client,headers,path = family
    grant_badges(client,headers,1,5,'#4eb478')
    fund(client,headers,'coupon',2)
    with connect(path) as db:
        db.execute('DROP TABLE coupon_request_badges'); db.execute('DROP TABLE coupon_requests')
    init_db(path)
    assert path.with_name(path.name+'.pre-coupon-requests.db').is_file()
    assert balance(client,'coupon')==2
    assert client.get('/api/dashboard/1').json()['badge_progress']['available']==5
    assert client.get('/api/coupon-requests').json()['total']==0
    assert_balanced(path)
