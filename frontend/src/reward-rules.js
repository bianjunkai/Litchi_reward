export const badgeColors = [
  { value: '#4eb478', label: '绿色' }, { value: '#f0aa37', label: '橙色' },
  { value: '#e55353', label: '红色' }, { value: '#d4af37', label: '金色' },
  { value: '#aab5c4', label: '银色' },
]

export const formatMoney = fen => (Number(fen) / 100).toFixed(2)

export function getSportsTasks(tasks, badges) {
  const badge = badges.find(item => item.code === 'sports' && item.active)
  return badge ? tasks.filter(task => task.active && task.badge_id === badge.id) : []
}

export function moneyToFen(value) {
  const text = String(value ?? '').trim()
  if (!/^\d{1,7}(\.\d{1,2})?$/.test(text)) return null
  const [yuan, fraction = ''] = text.split('.')
  const fen = Number(yuan) * 100 + Number(fraction.padEnd(2, '0'))
  return Number.isSafeInteger(fen) && fen <= 100000000 ? fen : null
}
