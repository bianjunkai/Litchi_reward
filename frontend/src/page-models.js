import { getSportsTasks } from './reward-rules.js'

const dailyCodes = { study: 'study_star', tidy: 'tidy_star', meal: 'meal_star' }

export function tasksForCategory(tasks, badges, category) {
  if (category === 'sports') return getSportsTasks(tasks, badges)
  if (Object.hasOwn(dailyCodes, category)) {
    return tasks.filter(task => !task.badge_id && task.asset_code === dailyCodes[category])
  }
  return tasks
}

export function homeChallenges(tasks, badges) {
  return [
    { id: 'study', name: '学习', icon: '📚', reward: '橙色星星', color: '#f08a24' },
    { id: 'tidy', name: '整理', icon: '🧸', reward: '绿色星星', color: '#41a85f' },
    { id: 'meal', name: '吃饭', icon: '🍚', reward: '红色星星', color: '#e55353' },
    { id: 'sports', name: '运动', icon: '🍄', reward: '体育徽章', color: '#629b45' },
  ].map(category => {
    const matching = tasksForCategory(tasks, badges, category.id)
    return { ...category, completed: matching.length > 0 && matching.every(task => task.claimed_today), enabled: matching.length > 0 }
  })
}

export function homeInventory(dashboard, badges) {
  const badge = code => badges.find(item => item.code === code)
  return [
    { id: 'stars', label: '星星', count: dashboard.star_total ?? dashboard.progress.total_stars, icon: 'star', color: '#f0aa37', section: 'stars', active: true },
    { id: 'life', label: '生活徽章', count: badge('life')?.available_count || 0, color: badge('life')?.color || '#f0aa37', section: 'badges', active: Boolean(badge('life')?.active) },
    { id: 'sports', label: '体育徽章', count: badge('sports')?.available_count || 0, color: badge('sports')?.color || '#4eb478', section: 'badges', active: Boolean(badge('sports')?.active) },
    { id: 'fire', label: '太阳花徽章', count: badge('fire')?.available_count || 0, color: badge('fire')?.color || '#f0aa37', section: 'badges', active: Boolean(badge('fire')?.active) },
    { id: 'coupons', label: '兑换券', count: dashboard.coupons.balance, icon: 'ticket', color: '#6685d9', section: 'coupons', active: true },
  ]
}
