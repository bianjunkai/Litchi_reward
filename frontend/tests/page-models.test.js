import test from 'node:test'
import assert from 'node:assert/strict'
import { homeChallenges, homeInventory, tasksForCategory } from '../src/page-models.js'

const badges = [
  { id: 17, code: 'sports', active: 1, earned_count: 8, available_count: 2 },
  { id: 19, code: 'life', active: 1, earned_count: 4, available_count: 1 },
  { id: 21, code: 'fire', active: 1, earned_count: 0, available_count: 0 },
]
const tasks = [
  { id: 1, asset_code: 'study_star', badge_id: null, active: 1, claimed_today: 1 },
  { id: 2, asset_code: 'tidy_star', badge_id: null, active: 1, claimed_today: 0 },
  { id: 3, asset_code: 'meal_star', badge_id: null, active: 1, claimed_today: 1 },
  { id: 4, asset_code: 'study_star', badge_id: 17, active: 1, claimed_today: 0 },
  { id: 5, asset_code: 'study_star', badge_id: 17, active: 1, claimed_today: 1 },
]

test('Daily task filters never mistake a badge task asset reference for a daily star reward', () => {
  assert.deepEqual(tasksForCategory(tasks, badges, 'study'), [tasks[0]])
  assert.deepEqual(tasksForCategory(tasks, badges, 'sports'), tasks.slice(3))
  assert.deepEqual(tasksForCategory(tasks, badges, 'all'), tasks)
})

test('The four home shortcuts show actual completion; sports requires all matching tasks', () => {
  const challenges = homeChallenges(tasks, badges)
  assert.deepEqual(challenges.map(item => item.completed), [true, false, true, false])
  assert.equal(challenges[3].reward, '体育徽章')
  assert.equal(homeChallenges(tasks.map(task => ({ ...task, claimed_today: 1 })), badges)[3].completed, true)
})

test('A disabled or missing sports task remains visible as a setup shortcut, not completed', () => {
  for (const configured of [[], [{ ...badges[0], active: 0 }]]) {
    const sports = homeChallenges(tasks, configured)[3]
    assert.equal(sports.enabled, false)
    assert.equal(sports.completed, false)
  }
})

test('Home shows available holdings, including the sunflower badge, not historical earnings', () => {
  const dashboard = { progress: { total_stars: 7 }, coupons: { balance: 3 } }
  const inventory = homeInventory(dashboard, badges)
  assert.deepEqual(inventory.map(item => item.count), [7, 1, 2, 0, 3])
  assert.deepEqual(inventory.map(item => item.id), ['stars', 'life', 'sports', 'fire', 'coupons'])
  assert.deepEqual(homeInventory(dashboard, []).slice(1, 4).map(item => item.active), [false, false, false])
})
