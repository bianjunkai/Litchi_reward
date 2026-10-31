export const childTabs = [
  { page: 'home', icon: 'castle', label: '城堡' },
  { page: 'adventures', icon: 'question', label: '冒险' },
  { page: 'backpack', icon: 'star', label: '背包' },
  { page: 'shop', icon: 'mushroom', label: '商城' },
]

export const parentTabs = [
  { id: 'today', label: '今日工作台' }, { id: 'exchange', label: '兑换中心' },
  { id: 'tasks', label: '任务管理' }, { id: 'products', label: '奖励上架' },
  { id: 'badges', label: '徽章管理' }, { id: 'records', label: '记录与纠错' },
  { id: 'settings', label: '家庭设置' },
]

export const backpackTabs = [
  { id: 'stars', label: '⭐ 星星袋' }, { id: 'badges', label: '🍄 徽章册' },
  { id: 'coupons', label: '🎟️ 兑换券' }, { id: 'rules', label: '奖励怎么玩' },
]

export const adventureTabs = [
  { id: 'all', label: '全部' }, { id: 'study', label: '📚 学习' },
  { id: 'tidy', label: '🧸 整理' }, { id: 'meal', label: '🍚 吃饭' },
  { id: 'sports', label: '🍄 体育' },
]

export const shopTabs = [{ id: 'catalog', label: '礼物架' }, { id: 'requests', label: '我的申请' }]

const sections = {
  home: [''], shop: shopTabs.map(tab => tab.id), adventures: adventureTabs.map(tab => tab.id),
  backpack: backpackTabs.map(tab => tab.id), parent: parentTabs.map(tab => tab.id),
}

export function parseRoute(hash = '') {
  const parts = hash.replace(/^#/, '').split('/').filter(Boolean)
  if (parts[0] === 'badges' && parts.length === 1) return { page: 'backpack', section: 'badges' }
  const page = Object.hasOwn(sections, parts[0]) && parts.length <= 2 ? parts[0] : 'home'
  const section = sections[page].includes(parts[1]) ? parts[1] : sections[page][0]
  return { page, section }
}

export function routeHash(page, section = '') {
  const route = parseRoute(`#/${page}/${section}`)
  return `#/${route.page}${route.section ? `/${route.section}` : ''}`
}
