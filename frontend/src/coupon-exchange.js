import { badgeColors } from './reward-rules.js'
import { isParentPage } from './parent.js'

export const couponRequestStates = { pending: '等待家长审批', approved: '已获得兑换券', rejected: '家长未同意', reversed: '已撤销，徽章已返还' }
export const colorName = color => badgeColors.find(item => item.value === color)?.label || '其他颜色'
export function couponBadgeChoices(badges) {
  return badges.filter(badge => badge.active && ['sports','life','fire','royal'].includes(badge.code))
    .flatMap(badge => (badge.colors || []).filter(variant => variant.available_count > 0).map(variant => ({
      key: `${badge.id}:${variant.color}`, badge_id: badge.id, name: badge.name, code: badge.code,
      color: variant.color, available: variant.available_count,
    })))
}
export function couponSelection(choices, counts) {
  const selections = choices.filter(item => counts[item.key] !== undefined && counts[item.key] !== 0)
    .map(item => ({badge_id:item.badge_id,color:item.color,count:counts[item.key]}))
  const total = selections.reduce((sum,item) => sum + (Number.isSafeInteger(item.count) ? item.count : 0),0)
  const valid = total === 5 && selections.every(item => Number.isSafeInteger(item.count) && item.count > 0
    && item.count <= Math.min(5, choices.find(choice => choice.badge_id === item.badge_id && choice.color === item.color).available))
    && Object.entries(counts).every(([key,count]) => count === 0 || choices.some(item => item.key === key))
  return { selections, total, valid }
}
export const isCouponRequestPage = body => isParentPage(body) && Number.isSafeInteger(body.pending_count) && body.pending_count >= 0
  && body.items.every(item => Object.hasOwn(couponRequestStates,item.status) && typeof item.can_approve === 'boolean'
    && typeof item.requested_at === 'string' && Array.isArray(item.selections)
    && item.selections.every(choice => Number.isSafeInteger(choice.badge_id) && choice.badge_id > 0
      && typeof choice.code === 'string' && typeof choice.name === 'string' && typeof choice.color === 'string'
      && Number.isSafeInteger(choice.count) && choice.count > 0)
    && item.selections.reduce((sum,choice) => sum + choice.count,0) === 5)
