from concurrent.futures import ThreadPoolExecutor

import pytest

from database import connect
from test_api import family, post, fund, balance, assert_balanced
from test_reward_rules import grant_badges


def get(client, headers, url, **params):
    response = client.get(url, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('url', ['/api/parent/review', '/api/parent/history', '/api/parent/operations/1/preview'])
def test_new_parent_views_require_session(family, url):
    client, headers, _ = family
    assert client.get(url).status_code == 401
    post(client, headers, '/api/auth/logout')
    assert client.get(url, headers=headers).status_code == 401


def test_review_paginates_past_old_cap_and_preserves_pending(family):
    client, headers, path = family
    with connect(path) as db:
        db.executemany('''INSERT INTO redemptions(child_id,product_id,status,requested_at,product_name,price)
            VALUES (1,1,?,'2026-10-18T01:00:00+00:00',?,1)''',
            [('pending', '最早等待的礼物')] + [('rejected', f'历史礼物{i}') for i in range(520)])
    pending = get(client, headers, '/api/parent/review')
    assert pending['total'] == pending['counts']['pending'] == 1
    assert pending['items'][0]['product_name'] == '最早等待的礼物'
    assert pending['coupon_balance'] == 0
    ids, cursor = [], None
    while True:
        params = {'status':'all', 'limit':100}
        if cursor:
            params['before_id'] = cursor
        result = get(client, headers, '/api/parent/review', **params)
        assert result['total'] == 521
        ids += [item['id'] for item in result['items']]
        if not result['has_more']:
            assert result['next_before_id'] is None
            break
        cursor = result['next_before_id']
    assert len(ids) == len(set(ids)) == 521 and ids == sorted(ids, reverse=True)


def test_history_pagination_changes_and_exact_id_search(family):
    client, headers, path = family
    first = fund(client, headers, 'study_star', 2)
    for _ in range(22):
        fund(client, headers, 'tidy_star', 1)
    page = get(client, headers, '/api/parent/history')
    assert page['total'] == 23 and len(page['items']) == 20 and page['has_more']
    rest = get(client, headers, '/api/parent/history', before_id=page['next_before_id'])
    assert len(rest['items']) == 3 and not rest['has_more']
    exact = get(client, headers, '/api/parent/history', search=f'#{first}')
    assert exact['total'] == 1 and exact['items'][0]['id'] == first
    assert exact['items'][0]['asset_changes'][0]['delta'] == 2
    assert get(client, headers, '/api/parent/history', kind='redemption')['total'] == 0
    assert get(client, headers, '/api/parent/history', search='#²')['total'] == 0
    assert_balanced(path)


@pytest.mark.parametrize('view', ['operations', 'ledger'])
def test_history_family_dates_and_literal_search(family, view):
    client, headers, path = family
    ids = [fund(client, headers) for _ in range(4)]
    with connect(path) as db:
        for op, stamp in zip(ids, ['2026-10-18T15:59:59Z','2026-10-18T16:00:00Z','2026-10-19T15:59:59+00:00','2026-10-19T16:00:00+00:00']):
            db.execute('UPDATE operations SET created_at=? WHERE id=?', (stamp,op))
            db.execute('UPDATE ledger SET created_at=? WHERE operation_id=?', (stamp,op))
        db.execute("UPDATE operations SET reason='文字%_\\原样' WHERE id=?", (ids[1],))
        db.execute("UPDATE ledger SET reason='文字%_\\原样' WHERE operation_id=?", (ids[1],))
    result = get(client, headers, '/api/parent/history', view=view, from_date='2026-10-19', to_date='2026-10-19')
    assert result['total'] == 2
    literal = get(client, headers, '/api/parent/history', view=view, search='%_\\')
    assert literal['total'] == 1
    assert get(client, headers, '/api/parent/history', view=view, search="' OR 1=1--")['total'] == 0


def test_parent_views_are_child_scoped(family):
    client, headers, path = family
    fund(client, headers)
    with connect(path) as db:
        db.execute("INSERT INTO children(id,name) VALUES (2,'另一个孩子')")
        db.execute('INSERT INTO child_assets SELECT 2,id,0 FROM asset_types')
        db.execute("INSERT INTO redemptions(child_id,product_id,requested_at,product_name) VALUES (2,1,'2026-10-19','孩子二的申请')")
    assert get(client, headers, '/api/parent/review')['total'] == 0
    assert get(client, headers, '/api/parent/summary')['pending_redemptions'] == 0
    assert get(client, headers, '/api/parent/summary', child_id=2)['pending_redemptions'] == 1
    assert get(client, headers, '/api/parent/history', child_id=2)['total'] == 0
    for url in ['/api/parent/review', '/api/parent/history', '/api/parent/summary']:
        assert client.get(url, headers=headers, params={'child_id':999}).status_code == 404


@pytest.mark.parametrize('url,params', [
    ('review', {'status':'bad'}), ('review', {'limit':0}), ('review', {'before_id':0}),
    ('review', {'from_date':'2026-10-20', 'to_date':'2026-10-19'}),
    ('review', {'to_date':'9999-12-31'}), ('history', {'view':'bad'}),
    ('history', {'kind':'bad'}), ('history', {'state':'bad'}), ('history', {'asset':'bad'}),
    ('history', {'direction':'bad'}), ('history', {'search':'a'*161}),
    ('history', {'from_date':'not-date'}), ('history', {'child_id':0}),
])
def test_parent_query_validation(family, url, params):
    client, headers, _ = family
    assert client.get('/api/parent/'+url, headers=headers, params=params).status_code == 422


def test_reversal_preview_is_read_only_and_matches_commit(family):
    client, headers, path = family
    op = fund(client, headers, 'study_star', 5)
    with connect(path) as db:
        before = {t:[tuple(row) for row in db.execute(f'SELECT * FROM {t}')] for t in ['operations','ledger','child_assets','audit_logs']}
    preview = get(client, headers, f'/api/parent/operations/{op}/preview')
    assert preview['can_reverse'] and not preview['blockers']
    assert preview['assets'][0]['before'] == 5 and preview['assets'][0]['delta'] == -5 and preview['assets'][0]['after'] == 0
    with connect(path) as db:
        after = {t:[tuple(row) for row in db.execute(f'SELECT * FROM {t}')] for t in before}
    assert before == after
    reverse = post(client, headers, f'/api/parent/operations/{op}/reverse')
    assert reverse.status_code == 200 and balance(client, 'study_star') == 0
    for blocked_op in [op, reverse.json()['operation_id']]:
        result = get(client, headers, f'/api/parent/operations/{blocked_op}/preview')
        assert not result['can_reverse'] and result['assets'] == []
    assert get(client, headers, '/api/parent/history', state='reversed')['total'] == 1
    assert get(client, headers, '/api/parent/history', state='reversal')['total'] == 1
    assert get(client, headers, '/api/parent/history', view='ledger', direction='out')['total'] == 1
    assert get(client, headers, '/api/parent/history', view='ledger', asset='coupon')['total'] == 0
    assert_balanced(path)


def test_badge_preview_dependencies_and_colored_restore(family):
    client, headers, path = family
    award = grant_badges(client, headers, 1, 5, '#4eb478')
    conversion = post(client, headers, '/api/parent/conversions/coupon', {}).json()['operation_id']
    preview = get(client, headers, f'/api/parent/operations/{award}/preview')
    assert not preview['can_reverse'] and preview['blocking_operation_ids'] == [conversion]
    assert preview['badges_remove'][0]['count'] == 5
    assert post(client, headers, f'/api/parent/operations/{award}/reverse').status_code == 409
    preview = get(client, headers, f'/api/parent/operations/{conversion}/preview')
    assert preview['can_reverse'] and preview['badges_restore'][0]['count'] == 5
    assert preview['badges_restore'][0]['color'] == '#4eb478'
    assert preview['assets'][0]['after'] == 0
    assert post(client, headers, f'/api/parent/operations/{conversion}/reverse').status_code == 200
    assert get(client, headers, f'/api/parent/operations/{award}/preview')['can_reverse']
    assert post(client, headers, f'/api/parent/operations/{award}/reverse').status_code == 200
    assert_balanced(path)


def test_reverse_rechecks_after_preview_and_insufficient_balance(family):
    client, headers, path = family
    op = fund(client, headers)
    assert get(client, headers, f'/api/parent/operations/{op}/preview')['can_reverse']
    item = client.post('/api/redemptions', json={'product_id':1}).json()['id']
    approved = post(client, headers, f'/api/parent/redemptions/{item}/approve', {'actual_amount_fen':3990})
    assert approved.status_code == 200
    blocked = get(client, headers, f'/api/parent/operations/{op}/preview')
    assert not blocked['can_reverse'] and blocked['assets'][0]['after'] == -1
    assert post(client, headers, f'/api/parent/operations/{op}/reverse').status_code == 409
    assert post(client, headers, f"/api/parent/operations/{approved.json()['operation_id']}/reverse").status_code == 200
    assert post(client, headers, f'/api/parent/operations/{op}/reverse').status_code == 200
    assert_balanced(path)


def test_adjustment_expected_balance_is_atomic_and_reason_is_required(family):
    client, headers, path = family
    payload = {'asset_code':'coupon','delta':1,'reason':'  补记说明  ','expected_balance':0}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: post(client,headers,'/api/parent/adjust',payload).status_code, range(2)))
    assert sorted(results) == [200,409] and balance(client,'coupon') == 1
    record = get(client, headers, '/api/parent/history')['items'][0]
    assert record['reason'] == '补记说明'
    for change in [{'reason':'  '},{'delta':1.5},{'expected_balance':True},{'delta':0}]:
        assert post(client,headers,'/api/parent/adjust',{**payload,**change}).status_code == 422
    assert get(client, headers, '/api/parent/history')['total'] == 1
    assert_balanced(path)


def test_missing_reversal_preview(family):
    client, headers, _ = family
    assert client.get('/api/parent/operations/999/preview',headers=headers).status_code == 404
