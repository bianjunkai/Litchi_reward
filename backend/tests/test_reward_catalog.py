import base64
import copy
from pathlib import Path

import pytest

from database import connect, init_db
from product_images import MAX_IMAGE_BYTES
from test_api import family, post, fund, assert_balanced

IMAGE = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aQb8AAAAASUVORK5CYII='
REWARD = {'name':'木马王国门票券','description':'和家长约定日期后使用','icon':'🎠','price':1,'cash_price_fen':3990,'image_data':IMAGE,'active':False}


def products(client, headers):
    return client.get('/api/parent/products',headers=headers).json()


def economics(path):
    with connect(path) as db:
        return {table:[tuple(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                for table in ['child_assets','ledger','operations','child_badges','task_claims','redemptions']}


def test_create_draft_publish_and_unlist_never_change_wallet(family):
    client, headers, path = family
    before = economics(path)
    result = post(client,headers,'/api/parent/products',REWARD)
    assert result.status_code == 200, result.text
    item_id = result.json()['id']
    assert item_id not in {item['id'] for item in client.get('/api/shop').json()}
    assert next(item for item in products(client,headers) if item['id']==item_id)['image_data'] == IMAGE
    for active in [True,True,False]:
        response = client.patch(f'/api/parent/products/{item_id}/availability',headers=headers,json={'active':active})
        assert response.status_code == 200
        assert (item_id in {item['id'] for item in client.get('/api/shop').json()}) == active
        assert economics(path) == before
    assert_balanced(path)


def test_product_writes_and_availability_require_parent_session(family):
    client, _, _ = family
    assert client.post('/api/parent/products',json=REWARD).status_code == 401
    assert client.put('/api/parent/products/1',json=REWARD).status_code == 401
    assert client.patch('/api/parent/products/1/availability',json={'active':False}).status_code == 401


@pytest.mark.parametrize('change', [{'name':'   '},{'price':0},{'price':6},{'price':1.5},{'price':'1'},
                                  {'cash_price_fen':3990.5},{'cash_price_fen':-1}])
def test_catalog_validation_rejects_invalid_terms_without_mutations(family, change):
    client, headers, path = family
    count = len(products(client,headers)); before = economics(path)
    assert post(client,headers,'/api/parent/products',{**REWARD,**change}).status_code == 422
    assert len(products(client,headers)) == count and economics(path) == before


@pytest.mark.parametrize('image', ['https://example.com/photo.png','javascript:alert(1)',
    'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=', 'data:image/png;base64,bm90YW5pbWFnZQ==',
    'data:image/png;base64,???', None,
    'data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'x'*MAX_IMAGE_BYTES).decode()])
def test_catalog_rejects_external_active_malformed_and_oversized_images(family,image):
    client, headers, _ = family
    assert post(client,headers,'/api/parent/products',{**REWARD,'image_data':image}).status_code == 422


def test_edit_and_unlist_preserve_pending_request_snapshot(family):
    client, headers, path = family
    item_id = post(client,headers,'/api/parent/products',{**REWARD,'active':True}).json()['id']
    quote = {key:REWARD[key] for key in ['name','description','icon','price','cash_price_fen','image_data']}
    request = client.post('/api/redemptions',json={'product_id':item_id,'expected_product':quote})
    assert request.status_code == 200
    request_id = request.json()['id']
    updated = {**REWARD,'name':'修改后的奖励','price':2,'cash_price_fen':7980,'image_data':'','active':False}
    assert client.put(f'/api/parent/products/{item_id}',headers=headers,json=updated).status_code == 200
    retry = client.post('/api/redemptions',json={'product_id':item_id,'expected_product':quote})
    assert retry.json()['id'] == request_id
    original = client.get('/api/shop/requests').json()['items'][0]
    assert original['product_name'] == REWARD['name'] and original['price'] == 1 and original['quoted_amount_fen'] == 3990
    assert not original['product_available']
    assert post(client,headers,f'/api/parent/redemptions/{request_id}/reject').status_code == 200
    assert client.post('/api/redemptions',json={'product_id':item_id}).status_code == 404
    assert_balanced(path)


def test_legacy_edits_keep_image_and_current_quotes_detect_changed_image(family):
    client, headers, _ = family
    item_id = post(client,headers,'/api/parent/products',{**REWARD,'active':True}).json()['id']
    old_edit = {key:value for key,value in REWARD.items() if key != 'image_data'}
    assert client.put(f'/api/parent/products/{item_id}',headers=headers,json={**old_edit,'active':True}).status_code == 200
    assert next(item for item in products(client,headers) if item['id']==item_id)['image_data'] == IMAGE
    assert client.put(f'/api/parent/products/{item_id}',headers=headers,json={**REWARD,'active':True,'image_data':''}).status_code == 200
    quote = {key:REWARD[key] for key in ['name','description','icon','price','cash_price_fen','image_data']}
    assert client.post('/api/redemptions',json={'product_id':item_id,'expected_product':quote}).status_code == 409
    quote.pop('image_data')
    assert client.post('/api/redemptions',json={'product_id':item_id,'expected_product':quote}).status_code == 200


def test_availability_is_strict_and_can_unlist_invalid_legacy_products(family):
    client, headers, path = family
    assert client.patch('/api/parent/products/999/availability',headers=headers,json={'active':True}).status_code == 404
    assert client.patch('/api/parent/products/1/availability',headers=headers,json={'active':'false'}).status_code == 422
    with connect(path) as db:
        db.execute('UPDATE products SET price=9 WHERE id=1')
    assert client.patch('/api/parent/products/1/availability',headers=headers,json={'active':False}).status_code == 200
    assert client.patch('/api/parent/products/1/availability',headers=headers,json={'active':True}).status_code == 422


def test_image_backup_roundtrip_and_old_backups_without_image(family):
    client, headers, path = family
    fund(client,headers)
    item_id = post(client,headers,'/api/parent/products',REWARD).json()['id']
    backup = client.get('/api/parent/backup',headers=headers).json()
    before = economics(path)
    assert post(client,headers,'/api/parent/restore',backup).status_code == 200
    assert economics(path) == before
    assert next(item for item in products(client,headers) if item['id']==item_id)['image_data'] == IMAGE
    old = copy.deepcopy(backup)
    for item in old['tables']['products']:
        item.pop('image_data')
    assert post(client,headers,'/api/parent/restore',old).status_code == 200
    assert all(item['image_data']=='' for item in products(client,headers))
    assert economics(path) == before
    assert_balanced(path)


def test_invalid_backup_image_is_rejected_without_replacing_data(family):
    client, headers, path = family
    backup = client.get('/api/parent/backup',headers=headers).json()
    original = copy.deepcopy(backup['tables'])
    backup['tables']['products'][0]['image_data'] = 'data:image/svg+xml;base64,PHN2Zy8+'
    assert post(client,headers,'/api/parent/restore',backup).status_code == 422
    assert client.get('/api/parent/backup',headers=headers).json()['tables'] == original
    assert not (path.parent/'backups').exists()


def test_image_schema_upgrade_is_additive_backed_up_and_repeatable(family):
    client, headers, path = family
    fund(client,headers,'study_star',3)
    with connect(path) as db:
        db.execute('ALTER TABLE products DROP COLUMN image_data')
    before = economics(path)
    init_db(path)
    safety = Path(str(path)+'.pre-product-images.db')
    assert safety.exists()
    with connect(safety) as db:
        assert 'image_data' not in {row['name'] for row in db.execute('PRAGMA table_info(products)')}
    assert economics(path) == before
    assert all(item['image_data']=='' for item in products(client,headers))
    safety_bytes = safety.read_bytes()
    init_db(path)
    assert safety.read_bytes() == safety_bytes and economics(path) == before
    assert_balanced(path)
