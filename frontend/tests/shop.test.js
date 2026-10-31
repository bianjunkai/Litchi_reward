import test from 'node:test'
import assert from 'node:assert/strict'
import { filterProducts, isShopRequests, productQuote, requestLabel } from '../src/shop.js'

const product = { id: 1, name: '木马王国门票', description: '周末一起去玩', icon: '🎠', price: 1, cash_price_fen: null, active: 1 }
const item = { id: 2, product_id: 1, product_name: product.name, icon: product.icon, price: 1, status: 'pending',
  requested_at: '2026-10-19T00:00:00Z', rule_version: 'family-v1', product_available: true, can_reapply: false,
  coupon_value_fen: 3990, quoted_amount_fen: null, actual_amount_fen: null }
const page = () => ({ child_id: 1, items: [item], total: 1, counts: { pending: 1, approved: 0, rejected: 0, reversed: 0 },
  pending_product_ids: [1], has_more: false, next_before_id: null })

test('Request history validates child, status counters and pending identities', () => {
  assert.equal(isShopRequests(page(), 1), true)
  assert.equal(isShopRequests(page(), 2), false)
  for (const changed of [{ pending_product_ids: [] }, { pending_product_ids: [1, 1] }, { total: 2 }, { counts: { pending: -1 } }]) {
    assert.equal(isShopRequests({ ...page(), ...changed }, 1), false)
  }
})

test('Request pagination requires descending unique ids and the exact next cursor', () => {
  assert.equal(isShopRequests({ ...page(), has_more: true, next_before_id: 2 }, 1), true)
  assert.equal(isShopRequests({ ...page(), has_more: true, next_before_id: 1 }, 1), false)
  assert.equal(isShopRequests({ ...page(), items: [item, item], total: 2, counts: { ...page().counts, pending: 2 } }, 1), false)
})

test('A pending or unlisted gift cannot offer reapplication', () => {
  assert.equal(isShopRequests({ ...page(), items: [{ ...item, can_reapply: true }] }, 1), false)
  const rejected = { ...item, status: 'rejected', can_reapply: true }
  const data = { ...page(), items: [rejected], counts: { pending: 0, rejected: 1, approved: 0, reversed: 0 }, pending_product_ids: [] }
  assert.equal(isShopRequests(data, 1), true)
  assert.equal(isShopRequests({ ...data, items: [{ ...rejected, product_available: false }] }, 1), false)
})

test('Settlement quantities and money stay integers, while old missing amounts remain unknown', () => {
  const approved = { ...item, status: 'approved', coupons_used: 2, actual_amount_fen: 5000, parent_top_up_fen: 0, forfeited_fen: 2980 }
  const data = { ...page(), items: [approved], counts: { pending: 0, approved: 1, rejected: 0, reversed: 0 }, pending_product_ids: [] }
  assert.equal(isShopRequests(data, 1), true)
  assert.equal(isShopRequests({ ...data, items: [{ ...approved, actual_amount_fen: 50.5 }] }, 1), false)
  assert.equal(isShopRequests({ ...data, items: [{ ...approved, actual_amount_fen: null, coupon_value_fen: null, rule_version: 'legacy' }] }, 1), true)
})

test('Shelf search and coupon filters do not hide unaffordable gifts by default', () => {
  const products = [product, { ...product, id: 2, name: '自选小玩具', price: 2 }]
  assert.deepEqual(filterProducts(products, '', 'all', 0), products)
  assert.deepEqual(filterProducts(products, '  门票 ', 'all', 0), [product])
  assert.deepEqual(filterProducts(products, '', 'enough', 1), [product])
  assert.equal(filterProducts(products, '', 'need', 1)[0].id, 2)
})

test('Confirmation sends only the displayed product quote, not account or admin fields', () => {
  assert.deepEqual(productQuote({ ...product, pin: 'never-send', balance: 99 }), {
    name: product.name, description: product.description, icon: product.icon, price: 1, cash_price_fen: null, image_data:'',
  })
  assert.equal(requestLabel('approved'), '已兑换')
  assert.equal(requestLabel('reversed'), '已撤销')
})
