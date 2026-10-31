import pytest

from database import connect
from test_api import family, post, fund, balance, assert_balanced
from test_reward_rules import grant_badges, set_badge_active


def history(client, wallet='stars', **filters):
    result = client.get('/api/backpack/ledger', params={'wallet': wallet, **filters})
    assert result.status_code == 200, result.text
    return result.json()


def badges(client, **filters):
    result = client.get('/api/backpack/badges', params=filters)
    assert result.status_code == 200, result.text
    return result.json()


def test_backpack_empty_and_read_only_without_parent_session(family):
    client, _, path = family
    before = path.read_bytes()
    for wallet in ('stars', 'coupon'):
        assert history(client, wallet) == {'child_id': 1, 'wallet': wallet, 'items': [], 'total': 0,
                                          'has_more': False, 'next_before_id': None}
    assert badges(client)['items'] == []
    assert path.read_bytes() == before
    assert client.post('/api/backpack/ledger').status_code == 405
    assert client.post('/api/backpack/badges').status_code == 405
    assert client.get('/api/parent/ledger').status_code == 401


@pytest.mark.parametrize('endpoint', ['/api/backpack/ledger', '/api/backpack/badges'])
def test_unknown_child_is_404(family, endpoint):
    client, _, _ = family
    assert client.get(endpoint, params={'child_id': 999}).status_code == 404


@pytest.mark.parametrize('query', [
    {'wallet': 'badges'}, {'wallet': 'coupon', 'asset_code': 'study_star'},
    {'wallet': 'stars', 'asset_code': 'coupon'}, {'asset_code': "' OR 1=1 --"},
    {'direction': 'invalid'}, {'limit': 0}, {'limit': 101}, {'before_id': 0}, {'child_id': 0},
])
def test_invalid_ledger_filters_are_rejected(family, query):
    client, _, _ = family
    assert client.get('/api/backpack/ledger', params=query).status_code == 422


@pytest.mark.parametrize('query', [{'badge_id': 0}, {'color': 'red'}, {'status': 'pending'}, {'limit': 101}, {'before_id': -1}])
def test_invalid_badge_filters_are_rejected(family, query):
    client, _, _ = family
    assert client.get('/api/backpack/badges', params=query).status_code == 422


def test_mixed_star_spending_retains_color_balances_and_reasons(family):
    client, headers, path = family
    for task_id in (1, 2, 3):
        assert post(client, headers, f'/api/tasks/{task_id}/claim').status_code == 200
    fund(client, headers, 'tidy_star', 1)
    fund(client, headers, 'meal_star', 1)
    assert post(client, headers, '/api/parent/conversions/stars', {'badge_id': 2}).status_code == 200
    entries = history(client)
    assert entries['total'] == 8
    spent = history(client, direction='out')['items']
    assert {item['asset_code']: item['delta'] for item in spent} == {'study_star': -1, 'tidy_star': -2, 'meal_star': -2}
    assert all(item['balance_after'] == 0 and item['kind'] == 'stars_to_badge' for item in spent)
    assert {item['kind'] for item in entries['items']} == {'task', 'manual', 'stars_to_badge'}
    green = history(client, asset_code='tidy_star', direction='in')['items']
    assert [item['balance_after'] for item in green] == [2, 1]
    assert all(item['reason'] and item['status'] == 'recorded' and item['settlement'] is None for item in green)
    assert_balanced(path)


def test_star_reversal_is_not_presented_as_another_earned_reward(family):
    client, headers, path = family
    operation = post(client, headers, '/api/tasks/1/claim').json()['operation_id']
    assert post(client, headers, f'/api/parent/operations/{operation}/reverse').status_code == 200
    items = history(client)['items']
    assert [(item['delta'], item['status'], item['balance_after']) for item in items] == [(-1, 'reversal', 0), (1, 'reversed', 1)]
    assert items[0]['kind'] == 'reversal' and items[0]['source_kind'] == 'task'
    assert items[0]['reversal_of'] == operation
    assert_balanced(path)


def test_ledger_keyset_pagination_is_stable_when_new_records_arrive(family):
    client, headers, _ = family
    for _ in range(25):
        fund(client, headers, amount=1)
    first = history(client, 'coupon', limit=7)
    assert first['total'] == 25 and first['has_more']
    assert first['next_before_id'] == first['items'][-1]['id']
    fund(client, headers, amount=1)
    items = first['items'][:]
    cursor = first['next_before_id']
    while cursor:
        result = history(client, 'coupon', before_id=cursor, limit=7)
        items.extend(result['items'])
        cursor = result['next_before_id']
    assert len(items) == len({item['id'] for item in items}) == 25
    assert [item['balance_after'] for item in items] == list(range(25, 0, -1))
    assert history(client, 'coupon')['items'][0]['balance_after'] == 26


@pytest.mark.parametrize('amount,top_up,forfeited', [(3000, 0, 990), (5000, 1010, 0)])
def test_coupon_history_links_real_settlement_and_reversal(family, amount, top_up, forfeited):
    client, headers, path = family
    grant_badges(client, headers, 1, 5)
    assert post(client, headers, '/api/parent/conversions/coupon', {}).status_code == 200
    request_id = client.post('/api/redemptions', json={'product_id': 1}).json()['id']
    assert history(client, 'coupon')['total'] == 1  # Pending requests never appear as spending.
    result = post(client, headers, f'/api/parent/redemptions/{request_id}/approve',
                  {'actual_amount_fen': amount, 'approve_top_up': True})
    operation = result.json()['operation_id']
    assert result.status_code == 200
    spending = history(client, 'coupon', direction='out')['items'][0]
    assert spending['delta'] == -1 and spending['balance_after'] == 0
    assert spending['settlement']['actual_amount_fen'] == amount
    assert spending['settlement']['parent_top_up_fen'] == top_up
    assert spending['settlement']['forfeited_fen'] == forfeited
    assert 'child_name' not in spending['settlement']
    assert post(client, headers, f'/api/parent/operations/{operation}/reverse').status_code == 200
    entries = history(client, 'coupon')['items']
    assert [item['status'] for item in entries] == ['reversal', 'reversed', 'recorded']
    assert entries[0]['settlement'] == entries[1]['settlement']
    assert entries[0]['settlement']['actual_amount_fen'] == amount
    assert entries[0]['source_kind'] == 'redemption' and entries[0]['balance_after'] == 1
    assert balance(client, 'coupon') == 1
    assert_balanced(path)


def test_legacy_consumer_amounts_are_not_invented(family):
    client, headers, path = family
    fund(client, headers)
    request_id = client.post('/api/redemptions', json={'product_id': 1}).json()['id']
    operation = post(client, headers, f'/api/parent/redemptions/{request_id}/approve',
                     {'actual_amount_fen': 3990}).json()['operation_id']
    with connect(path) as db:
        db.execute("UPDATE operations SET rule_version='legacy' WHERE id=?", (operation,))
        db.execute("UPDATE redemptions SET rule_version='legacy',actual_amount_fen=NULL,coupons_used=NULL,coupon_value_fen=NULL,parent_top_up_fen=NULL,forfeited_fen=NULL WHERE operation_id=?", (operation,))
    item = history(client, 'coupon', direction='out')['items'][0]
    assert item['rule_version'] == 'legacy' and item['delta'] == -1
    assert item['settlement']['actual_amount_fen'] is None
    assert item['settlement']['coupon_value_fen'] is None


def test_pre_reconciliation_balances_are_unknown_instead_of_fabricated(family):
    client, _, path = family
    with connect(path) as db:
        coupon = db.execute("SELECT id FROM asset_types WHERE code='coupon'").fetchone()[0]
        db.execute("INSERT INTO ledger(child_id,asset_type_id,delta,reason,created_at) VALUES (1,?,-1,'旧消费，收入记录不完整','2025-01-01T00:00:00Z')", (coupon,))
        db.execute("INSERT INTO ledger(child_id,asset_type_id,delta,reason,reference_type,created_at) VALUES (1,?,1,'旧版本余额对账补录（原始原因未知）','opening_balance','2025-01-02T00:00:00Z')", (coupon,))
    before = path.read_bytes()
    items = history(client, 'coupon')['items']
    assert items[0]['reference_type'] == 'opening_balance' and items[0]['balance_after'] == 0
    assert items[1]['balance_after'] is None and items[1]['delta'] == -1
    assert path.read_bytes() == before
    assert_balanced(path)


def test_badge_statuses_preserve_collection_and_follow_reversals(family):
    client, headers, _ = family
    grant_operation = grant_badges(client, headers, 1, 7, '#aab5c4')
    conversion = post(client, headers, '/api/parent/conversions/coupon', {}).json()['operation_id']
    assert badges(client, status='spent')['total'] == 5
    assert badges(client, status='available')['total'] == 2
    assert all(item['spent_at'] and item['reason'] for item in badges(client, status='spent')['items'])
    page = badges(client, limit=3)
    older = badges(client, limit=3, before_id=page['next_before_id'])
    assert not {item['id'] for item in page['items']} & {item['id'] for item in older['items']}
    assert badges(client, badge_id=1, color='#AAB5C4', status='spent')['total'] == 5
    assert post(client, headers, f'/api/parent/operations/{conversion}/reverse').status_code == 200
    assert badges(client, status='available')['total'] == 7
    assert badges(client, status='spent')['total'] == 0
    assert post(client, headers, f'/api/parent/operations/{grant_operation}/reverse').status_code == 200
    assert badges(client, status='reversed')['total'] == 7
    assert badges(client, status='available')['total'] == 0


def test_disabled_badges_keep_their_original_color_and_reason(family):
    client, headers, _ = family
    set_badge_active(client, headers, 3, True)
    grant_badges(client, headers, 3, 2, '#d4af37')
    set_badge_active(client, headers, 3, False)
    page = badges(client, badge_id=3, status='disabled', color='#d4af37')
    assert page['total'] == 2
    assert all(item['color'] == '#d4af37' and item['reason'] for item in page['items'])
    assert badges(client, status='available')['total'] == 0
    assert badges(client, badge_id=999)['items'] == []


def test_history_is_scoped_to_one_child_and_does_not_expose_auth(family):
    client, headers, path = family
    with connect(path) as db:
        db.execute("INSERT INTO children(id,name) VALUES (2,'另一个孩子')")
        db.execute('INSERT INTO child_assets SELECT 2,id,0 FROM asset_types')
        db.execute("INSERT INTO child_badges(child_id,badge_id,reason,earned_at,color) VALUES (2,1,'另一个孩子的运动','2026-10-18T16:01:00+00:00','#4eb478')")
    assert post(client, headers, '/api/parent/adjust', {'child_id': 2, 'asset_code': 'coupon', 'delta': 2, 'reason': '另一个孩子的补记'}).status_code == 200
    assert history(client, 'coupon')['total'] == 0
    assert badges(client)['total'] == 0
    assert history(client, 'coupon', child_id=2)['items'][0]['delta'] == 2
    assert badges(client, child_id=2)['items'][0]['reason'] == '另一个孩子的运动'
    page = history(client, 'coupon', child_id=2)
    assert set(page) == {'child_id', 'wallet', 'items', 'total', 'has_more', 'next_before_id'}
    assert not {'pin_hash', 'token_hash', 'child_name'} & set(page['items'][0])
    before = path.read_bytes()
    for _ in range(3):
        history(client, 'coupon', child_id=2)
        badges(client, child_id=2)
    assert path.read_bytes() == before
