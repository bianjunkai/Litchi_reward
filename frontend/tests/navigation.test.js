import test from 'node:test'
import assert from 'node:assert/strict'
import { childTabs, parentTabs, backpackTabs, adventureTabs, parseRoute, routeHash } from '../src/navigation.js'

test('Child navigation has exactly four destinations, not an administrative tab', () => {
  assert.deepEqual(childTabs.map(tab => tab.page), ['home', 'adventures', 'backpack', 'shop'])
  assert.deepEqual(parseRoute(), { page: 'home', section: '' })
  assert.deepEqual(parseRoute('#/badges'), { page: 'backpack', section: 'badges' })
})

test('All subpages round-trip through shareable, reload-safe hash routes', () => {
  for (const [page, tabs] of [['parent', parentTabs], ['backpack', backpackTabs], ['adventures', adventureTabs]]) {
    for (const tab of tabs) assert.deepEqual(parseRoute(routeHash(page, tab.id)), { page, section: tab.id })
  }
  assert.deepEqual(parseRoute('#/shop'), { page: 'shop', section: '' })
  assert.deepEqual(parseRoute('#/parent'), { page: 'parent', section: 'today' })
})

test('Unknown or malformed locations cannot become arbitrary pages or sections', () => {
  for (const hash of ['#/unknown', '#/__proto__', '#/constructor', '#/parent/tasks/extra', '#/https:evil']) {
    assert.deepEqual(parseRoute(hash), { page: 'home', section: '' })
  }
  assert.deepEqual(parseRoute('#/parent/unknown'), { page: 'parent', section: 'today' })
  assert.deepEqual(parseRoute('#/backpack/unknown'), { page: 'backpack', section: 'stars' })
})
