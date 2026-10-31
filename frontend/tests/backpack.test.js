import test from 'node:test'
import assert from 'node:assert/strict'
import { formatHistoryTime, historyAction, historyStatus, isBackpackPage } from '../src/backpack.js'

const ledger = { id: 8, asset_code: 'study_star', asset_name: '学习星星', delta: 1, balance_after: 3,
  kind: 'task', status: 'recorded', rule_version: 'family-v1', reason: '认真读书', created_at: '2026-10-18T16:01:00Z', settlement: null }
const page = (items = [ledger], wallet = 'stars') => ({ child_id: 1, wallet, items, total: items.length, has_more: false, next_before_id: null })

test('Child ledger pages validate account, wallet, integer quantities and ordering', () => {
  assert.equal(isBackpackPage(page(), 'stars', 1), true)
  assert.equal(isBackpackPage(page(), 'stars', 2), false)
  assert.equal(isBackpackPage(page(), 'coupon', 1), false)
  assert.equal(isBackpackPage(page([{ ...ledger, rule_version: 'legacy', balance_after: null }]), 'stars', 1), true)
  for (const changed of [{ delta: 0.5 }, { balance_after: -1 }, { asset_code: 'coupon' }, { status: 'approved' }]) {
    assert.equal(isBackpackPage(page([{ ...ledger, ...changed }]), 'stars', 1), false)
  }
  assert.equal(isBackpackPage(page([ledger, ledger]), 'stars', 1), false)
  assert.equal(isBackpackPage(page([{ ...ledger, id: 7 }, ledger]), 'stars', 1), false)
})

test('Paging cursors must match the last record, preventing duplicate endless pages', () => {
  const data = { ...page(), has_more: true, next_before_id: 8 }
  assert.equal(isBackpackPage(data, 'stars', 1), true)
  for (const next_before_id of [null, 0, 7]) assert.equal(isBackpackPage({ ...data, next_before_id }, 'stars', 1), false)
  assert.equal(isBackpackPage({ ...page([]), has_more: true, next_before_id: 8 }, 'stars', 1), false)
})

test('Badge history supports available, spent, disabled and reversed instances', () => {
  const badge = { id: 1, badge_id: 17, name: '体育徽章', code: 'sports', color: '#4eb478',
    earned_at: '2026-10-18T16:01:00Z', reason: '完成运动目标', rule_version: 'family-v1' }
  for (const status of ['available', 'spent', 'disabled', 'reversed']) {
    assert.equal(isBackpackPage(page([{ ...badge, status }], 'badges'), 'badges', 1), true)
  }
  assert.equal(isBackpackPage(page([{ ...badge, status: 'pending' }], 'badges'), 'badges', 1), false)
})

test('Coupon settlements retain integer fen, including legacy unknown amounts', () => {
  const item = { ...ledger, asset_code: 'coupon', kind: 'redemption', delta: -1,
    settlement: { product_name: '木马王国门票', rule_version: 'family-v1', coupons_used: 1, coupon_value_fen: 3990,
      actual_amount_fen: 3000, parent_top_up_fen: 0, forfeited_fen: 990 } }
  assert.equal(isBackpackPage(page([item], 'coupon'), 'coupon', 1), true)
  assert.equal(isBackpackPage(page([{ ...item, settlement: { ...item.settlement, actual_amount_fen: 30.5 } }], 'coupon'), 'coupon', 1), false)
  assert.equal(isBackpackPage(page([{ ...item, rule_version: 'legacy', settlement: { product_name: '旧消费', rule_version: 'legacy', actual_amount_fen: null } }], 'coupon'), 'coupon', 1), true)
})

test('Reversal language distinguishes refunds, clawbacks and earned rewards', () => {
  assert.equal(historyAction({ kind: 'reversal', delta: 1 }), '撤销返还')
  assert.equal(historyAction({ kind: 'reversal', delta: -1 }), '撤销扣回')
  assert.equal(historyAction(ledger), '任务奖励')
  assert.equal(historyAction({ kind: 'legacy', reference_type: 'opening_balance' }), '历史余额对账补录')
  assert.equal(historyStatus({ status: 'reversed' }, 'stars'), '原操作已撤销')
  assert.equal(historyStatus({ status: 'spent' }, 'badges'), '已兑换')
})

test('History dates use family time across midnight and tolerate unknown legacy times', () => {
  assert.match(formatHistoryTime('2026-10-18T15:59:00Z'), /2026\/10\/18.*23:59/)
  assert.match(formatHistoryTime('2026-10-18T16:01:00Z'), /2026\/10\/19.*00:01/)
  assert.equal(formatHistoryTime('legacy unknown'), '历史时间未记录')
  assert.equal(formatHistoryTime(null), '历史时间未记录')
})
