import test from 'node:test'
import assert from 'node:assert/strict'
import { moneyToFen, formatMoney, getSportsTasks } from '../src/reward-rules.js'

test('Coupon values use exact integer fen, including the five-coupon cap', () => {
  assert.equal(moneyToFen('39.9'), 3990)
  assert.equal(moneyToFen('39.90'), 3990)
  assert.equal(moneyToFen('199.50'), 19950)
  assert.equal(moneyToFen('0'), 0)
  assert.equal(formatMoney(5 * 3990), '199.50')
  assert.equal(formatMoney(5000 - 3990), '10.10')
  assert.equal(formatMoney(3990 - 3000), '9.90')
})

test('Invalid or sub-fen amounts are rejected instead of rounded', () => {
  for (const value of ['', ' ', null, '-1', '39.901', '1e3', 'NaN', '999999999', '￥39.90']) {
    assert.equal(moneyToFen(value), null, `reject ${value}`)
  }
})

test('Sports entry selects only enabled sports badge tasks, without assuming a badge ID', () => {
  const badges = [{ id: 17, code: 'sports', active: 1 }, { id: 1, code: 'life', active: 1 }]
  const tasks = [
    { id: 1, badge_id: null, active: 1 },
    { id: 2, badge_id: 17, active: 1, amount: 2, claimed_today: 1 },
    { id: 3, badge_id: 1, active: 1 },
    { id: 4, badge_id: 17, active: 0 },
  ]
  assert.deepEqual(getSportsTasks(tasks, badges), [tasks[1]])
  assert.deepEqual(getSportsTasks(tasks, [{ ...badges[0], active: 0 }]), [])
  assert.deepEqual(getSportsTasks(tasks, []), [])
  assert.deepEqual(getSportsTasks([{ id: 1, active: 1 }], []), [])
})
