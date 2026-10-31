from concurrent.futures import ThreadPoolExecutor

import pytest

from database import connect
from test_api import family, post, fund, balance, assert_balanced


def quote(product):
    return {key: product[key] for key in ('name', 'description', 'icon', 'price', 'cash_price_fen')}


def apply(client, product_id=1, **extra):
    return client.post('/api/redemptions', json={'product_id': product_id, **extra})


def requests(client, **filters):
    response = client.get('/api/shop/requests', params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def test_child_requests_are_read_only_and_empty_without_parent_login(family):
    client, _, path = family
    before = path.read_bytes()
    assert requests(client) == {'child_id': 1, 'items': [], 'total': 0,
        'counts': {'pending': 0, 'approved': 0, 'rejected': 0, 'reversed': 0},
        'pending_product_ids': [], 'has_more': False, 'next_before_id': None}
    assert path.read_bytes() == before
    assert client.post('/api/shop/requests').status_code == 405
    assert client.post('/api/parent/redemptions/1/approve', json={'actual_amount_fen': 3990}).status_code == 401


def test_zero_balance_application_saves_quote_without_spending(family):
    client, _, path = family
    product = client.get('/api/shop').json()[0]
    result = apply(client, expected_product=quote(product))
    assert result.status_code == 200
    page = requests(client)
    item = page['items'][0]
    assert item['product_name'] == product['name'] and item['price'] == 1
    assert item['status'] == 'pending' and item['coupon_value_fen'] == 3990
    assert item['coupons_used'] is None and item['actual_amount_fen'] is None
    assert page['pending_product_ids'] == [1] and page['counts']['pending'] == 1
    assert item['can_reapply'] is False
    assert balance(client, 'coupon') == 0
    assert client.get('/api/backpack/ledger?wallet=coupon').json()['total'] == 0
    assert_balanced(path)


def test_concurrent_duplicate_application_has_one_pending_record(family):
    client, _, path = family
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply(client), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert len({result.json()['id'] for result in results}) == 1
    assert requests(client)['total'] == 1
    assert balance(client, 'coupon') == 0
    assert_balanced(path)


@pytest.mark.parametrize('changed', [
    {'name': '更新后的门票'}, {'description': '新的消费约定'}, {'icon': '🎡'}, {'price': 2}, {'cash_price_fen': 0},
])
def test_stale_product_quote_cannot_silently_apply_different_terms(family, changed):
    client, headers, _ = family
    product = client.get('/api/shop').json()[0]
    current = {**product, **changed}
    assert client.put('/api/parent/products/1', headers=headers, json=current).status_code == 200
    stale = apply(client, expected_product=quote(product))
    assert stale.status_code == 409 and '刷新' in stale.json()['detail']
    assert requests(client)['total'] == 0
    assert apply(client, expected_product=quote(current)).status_code == 200
    item = requests(client)['items'][0]
    assert item['product_name'] == current['name'] and item['price'] == current['price']
    assert item['quoted_amount_fen'] == current['cash_price_fen']


def test_pending_retry_after_edit_or_unlisting_preserves_original_request(family):
    client, headers, _ = family
    original = client.get('/api/shop').json()[0]
    first = apply(client, expected_product=quote(original)).json()
    updated = {**original, 'name': '下架后的名称', 'price': 3, 'cash_price_fen': 5000, 'active': False}
    assert client.put('/api/parent/products/1', headers=headers, json=updated).status_code == 200
    retried = apply(client, expected_product=quote(original))
    assert retried.status_code == 200 and retried.json()['id'] == first['id']
    page = requests(client)
    assert page['total'] == 1
    assert page['items'][0]['product_name'] == original['name']
    assert page['items'][0]['price'] == 1 and page['items'][0]['quoted_amount_fen'] is None
    assert page['items'][0]['product_available'] is False
    assert page['items'][0]['can_reapply'] is False


def test_unlisted_product_cannot_receive_a_new_request(family):
    client, headers, _ = family
    product = client.get('/api/shop').json()[0]
    assert client.put('/api/parent/products/1', headers=headers, json={**product, 'active': False}).status_code == 200
    assert apply(client, expected_product=quote(product)).status_code == 404
    assert requests(client)['total'] == 0


def test_all_statuses_and_counts_are_independent_of_history_filters(family):
    client, headers, path = family
    fund(client, headers, amount=5)
    approved = apply(client, 1).json()['id']
    assert post(client, headers, f'/api/parent/redemptions/{approved}/approve', {'actual_amount_fen': 5000, 'coupon_count': 2}).status_code == 200
    rejected = apply(client, 2).json()['id']
    assert post(client, headers, f'/api/parent/redemptions/{rejected}/reject').status_code == 200
    reversed_id = apply(client, 3).json()['id']
    operation = post(client, headers, f'/api/parent/redemptions/{reversed_id}/approve', {'actual_amount_fen': 3990}).json()['operation_id']
    assert post(client, headers, f'/api/parent/operations/{operation}/reverse').status_code == 200
    apply(client, 4)
    for status in ('pending', 'approved', 'rejected', 'reversed'):
        page = requests(client, status=status, limit=1)
        assert page['counts'] == {'pending': 1, 'approved': 1, 'rejected': 1, 'reversed': 1}
        assert page['pending_product_ids'] == [4]
        assert page['total'] == 1 and page['items'][0]['status'] == status
    item = requests(client, status='approved')['items'][0]
    assert item['price'] == 1 and item['coupons_used'] == 2
    assert item['actual_amount_fen'] == 5000 and item['forfeited_fen'] == 2980
    assert item['parent_top_up_fen'] == 0
    assert requests(client, status='reversed')['items'][0]['reversed_at']
    assert balance(client, 'coupon') == 3
    assert_balanced(path)


def test_rejected_reapplication_creates_new_history_without_debit(family):
    client, headers, _ = family
    first = apply(client).json()['id']
    assert post(client, headers, f'/api/parent/redemptions/{first}/reject').status_code == 200
    assert requests(client)['items'][0]['can_reapply'] is True
    second = apply(client).json()['id']
    assert second != first
    page = requests(client, status='rejected')
    assert page['items'][0]['status'] == 'rejected' and page['items'][0]['can_reapply'] is False
    assert page['pending_product_ids'] == [1]
    assert page['counts']['pending'] == page['counts']['rejected'] == 1
    assert balance(client, 'coupon') == 0


def test_paginated_history_does_not_lose_rows_when_a_new_request_arrives(family):
    client, headers, _ = family
    for _ in range(25):
        item = apply(client).json()['id']
        assert post(client, headers, f'/api/parent/redemptions/{item}/reject').status_code == 200
    first = requests(client, status='rejected', limit=6)
    late = apply(client).json()['id']
    post(client, headers, f'/api/parent/redemptions/{late}/reject')
    items = first['items'][:]
    cursor = first['next_before_id']
    while cursor:
        page = requests(client, status='rejected', limit=6, before_id=cursor)
        items.extend(page['items'])
        cursor = page['next_before_id']
    assert len(items) == len({item['id'] for item in items}) == 25
    assert late not in {item['id'] for item in items}
    assert requests(client)['total'] == 26


def test_legacy_amounts_are_not_recalculated_and_invalid_future_price_is_not_available(family):
    client, headers, path = family
    fund(client, headers)
    item_id = apply(client).json()['id']
    post(client, headers, f'/api/parent/redemptions/{item_id}/approve', {'actual_amount_fen': 3990})
    with connect(path) as db:
        db.execute("UPDATE redemptions SET rule_version='legacy',actual_amount_fen=NULL,coupons_used=NULL,coupon_value_fen=NULL,parent_top_up_fen=NULL,forfeited_fen=NULL WHERE id=?", (item_id,))
        db.execute('UPDATE products SET price=6 WHERE id=1')
    before = path.read_bytes()
    item = requests(client)['items'][0]
    assert item['actual_amount_fen'] is None and item['coupon_value_fen'] is None
    assert item['price'] == 1 and item['product_available'] is False and item['can_reapply'] is False
    assert path.read_bytes() == before
    assert apply(client).status_code == 422


def test_requests_are_child_scoped_and_do_not_expose_management_data(family):
    client, _, path = family
    with connect(path) as db:
        db.execute("INSERT INTO children(id,name) VALUES (2,'另一位孩子')")
        db.execute('INSERT INTO child_assets SELECT 2,id,0 FROM asset_types')
    apply(client, child_id=2)
    assert requests(client)['total'] == 0 and requests(client)['pending_product_ids'] == []
    other = requests(client, child_id=2)
    assert other['total'] == 1 and other['pending_product_ids'] == [1]
    assert not {'pin_hash', 'token_hash', 'child_name', 'operation_id'} & set(other['items'][0])
    assert client.get('/api/shop/requests?child_id=999').status_code == 404


@pytest.mark.parametrize('params', [{'child_id': 0}, {'status': 'cancelled'}, {'status': "' OR 1=1 --"}, {'before_id': 0}, {'limit': 0}, {'limit': 101}])
def test_invalid_history_queries_are_rejected(family, params):
    client, _, _ = family
    assert client.get('/api/shop/requests', params=params).status_code == 422


@pytest.mark.parametrize('price', [0, 6, 1.5, '1'])
def test_expected_quote_rejects_invalid_coupon_quantities(family, price):
    client, _, _ = family
    product = client.get('/api/shop').json()[0]
    assert apply(client, expected_product={**quote(product), 'price': price}).status_code == 422
