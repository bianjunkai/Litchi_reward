const integer = value => Number.isSafeInteger(value)
const positive = value => integer(value) && value > 0
const nonnegative = value => integer(value) && value >= 0
const ledgerStatuses = ['recorded', 'reversed', 'reversal']
export const badgeStatuses = [
  { value: 'all', label: '全部状态' }, { value: 'available', label: '可使用' },
  { value: 'spent', label: '已兑换' }, { value: 'disabled', label: '尚未启用' },
  { value: 'reversed', label: '已撤销' },
]

function isSettlement(value) {
  return value === null || Boolean(value && typeof value.product_name === 'string'
    && typeof value.rule_version === 'string'
    && (value.actual_amount_fen === null || (
      nonnegative(value.actual_amount_fen) && positive(value.coupons_used)
      && nonnegative(value.coupon_value_fen) && nonnegative(value.parent_top_up_fen) && nonnegative(value.forfeited_fen)
    )))
}

export function isBackpackPage(data, kind, childId) {
  if (!data || data.wallet !== kind || data.child_id !== childId || !Array.isArray(data.items)
    || !nonnegative(data.total) || data.total < data.items.length || typeof data.has_more !== 'boolean'
    || (data.has_more ? !positive(data.next_before_id) : data.next_before_id !== null)) return false
  if (data.has_more && data.next_before_id !== data.items.at(-1)?.id) return false
  return data.items.every((item, index) => item && positive(item.id)
    && (!index || item.id < data.items[index - 1].id) && typeof item.reason === 'string'
    && typeof item.rule_version === 'string'
    && (kind === 'badges'
      ? positive(item.badge_id) && typeof item.name === 'string' && typeof item.code === 'string'
        && typeof item.color === 'string' && typeof item.earned_at === 'string'
        && badgeStatuses.slice(1).some(status => status.value === item.status)
      : integer(item.delta) && (item.balance_after === null || nonnegative(item.balance_after)) && typeof item.asset_name === 'string'
        && (kind === 'coupon' ? item.asset_code === 'coupon' : ['study_star', 'tidy_star', 'meal_star', 'gold_star'].includes(item.asset_code))
        && typeof item.created_at === 'string' && typeof item.kind === 'string'
        && ledgerStatuses.includes(item.status) && isSettlement(item.settlement)))
}

export function historyAction(item) {
  if (item.reference_type === 'opening_balance') return '历史余额对账补录'
  if (item.kind === 'reversal') return item.delta > 0 ? '撤销返还' : '撤销扣回'
  return { task: '任务奖励', manual: '家长补记／纠错', stars_to_badge: '兑换生活徽章',
    badges_to_coupon: '徽章换券', redemption: '兑换礼物', legacy: '历史记账' }[item.kind] || '资产记录'
}

export function historyStatus(item, kind) {
  if (kind === 'badges') return badgeStatuses.find(status => status.value === item.status)?.label || '历史记录'
  return { recorded: '已记账', reversed: '原操作已撤销', reversal: '纠错记录' }[item.status] || '历史记录'
}

export function formatHistoryTime(value, timeZone = 'Asia/Shanghai') {
  const date = new Date(value)
  if (!value || !Number.isFinite(date.getTime())) return '历史时间未记录'
  return new Intl.DateTimeFormat('zh-CN', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date)
}
