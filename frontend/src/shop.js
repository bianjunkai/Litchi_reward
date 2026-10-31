export const requestStatuses = [
  { value: 'all', label: '全部' }, { value: 'pending', label: '等家长确认' },
  { value: 'approved', label: '已兑换' }, { value: 'rejected', label: '未通过' },
  { value: 'reversed', label: '已撤销' },
]
const statuses = requestStatuses.slice(1).map(item => item.value)
const positive = value => Number.isSafeInteger(value) && value > 0
const nonnegative = value => Number.isSafeInteger(value) && value >= 0

export function isShopRequests(data, childId) {
  if (!data || data.child_id !== childId || !Array.isArray(data.items) || !nonnegative(data.total)
    || data.total < data.items.length || typeof data.has_more !== 'boolean' || !data.counts || Object.keys(data.counts).length !== statuses.length
    || !statuses.every(status => nonnegative(data.counts[status]))
    || data.total > statuses.reduce((sum, status) => sum + data.counts[status], 0)
    || !Array.isArray(data.pending_product_ids) || !data.pending_product_ids.every(positive)
    || new Set(data.pending_product_ids).size !== data.pending_product_ids.length
    || data.pending_product_ids.length > data.counts.pending
    || (data.has_more ? !positive(data.next_before_id) || data.next_before_id !== data.items.at(-1)?.id : data.next_before_id !== null)) return false
  return data.items.every((item, index) => item && positive(item.id) && positive(item.product_id)
    && (!index || item.id < data.items[index - 1].id)
    && typeof item.product_name === 'string' && typeof item.icon === 'string' && positive(item.price)
    && statuses.includes(item.status) && typeof item.requested_at === 'string'
    && typeof item.rule_version === 'string' && typeof item.product_available === 'boolean' && typeof item.can_reapply === 'boolean'
    && (!item.can_reapply || (item.status !== 'pending' && item.product_available && !data.pending_product_ids.includes(item.product_id)))
    && (item.status !== 'pending' || data.pending_product_ids.includes(item.product_id))
    && (item.coupon_value_fen === null || nonnegative(item.coupon_value_fen))
    && (item.quoted_amount_fen === null || nonnegative(item.quoted_amount_fen))
    && (item.actual_amount_fen === null || (nonnegative(item.actual_amount_fen) && positive(item.coupons_used)
      && nonnegative(item.coupon_value_fen) && nonnegative(item.parent_top_up_fen) && nonnegative(item.forfeited_fen))))
}

export function productQuote(product) {
  return { name: product.name, description: product.description, icon: product.icon,
    price: product.price, cash_price_fen: product.cash_price_fen ?? null, image_data: product.image_data || '' }
}

export function filterProducts(products, search, affordability, balance) {
  const term = search.trim().toLocaleLowerCase()
  return products.filter(product => (!term || (product.name + ' ' + product.description).toLocaleLowerCase().includes(term))
    && (affordability === 'all' || (affordability === 'enough' ? product.price <= balance : product.price > balance)))
}

export function requestLabel(status) {
  return requestStatuses.find(item => item.value === status)?.label || '历史记录'
}
