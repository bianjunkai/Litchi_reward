import { computed, onBeforeUnmount, ref, watch } from 'vue'

export const operationNames = { task:'获得奖励', manual:'数据纠错', stars_to_badge:'代币换生活徽章', badges_to_coupon:'徽章换券', redemption:'使用兑换券', reversal:'撤销记录' }
export const signed = number => `${number > 0 ? '+' : ''}${number}`
export function adjustmentPreview(assets, draft) {
  const asset = assets.find(item => item.code === draft.asset_code && item.active)
  const valid = !!asset && Number.isInteger(draft.delta) && draft.delta !== 0 && Math.abs(draft.delta) <= 999
    && !!draft.reason.trim() && draft.reason.trim().length <= 160 && asset.balance + draft.delta >= 0
    && !(draft.asset_code === 'gold_star' && draft.delta > 0)
  return { valid, asset, after: asset ? asset.balance + draft.delta : null }
}
export function parentQuery(filters, cursor) {
  const params = new URLSearchParams({child_id:'1', limit:'20'})
  for (const [key,value] of Object.entries(filters)) if (value !== '' && value != null) params.set(key, value)
  if (cursor) params.set('before_id', cursor)
  return params.toString()
}
export const isParentPage = body => !!body && Array.isArray(body.items) && body.items.every((item,index) => Number.isSafeInteger(item.id) && item.id > 0 && (!index || item.id < body.items[index-1].id))
  && Number.isSafeInteger(body.total) && body.total >= body.items.length && typeof body.has_more === 'boolean'
  && (body.has_more ? Number.isSafeInteger(body.next_before_id) && body.next_before_id === body.items.at(-1)?.id : body.next_before_id === null)
export const isReviewPage = body => isParentPage(body) && Number.isSafeInteger(body.coupon_balance) && body.coupon_balance >= 0
  && ['pending','approved','rejected','reversed'].every(key => Number.isSafeInteger(body.counts?.[key]) && body.counts[key] >= 0)
  && body.items.every(item => ['pending','approved','rejected','reversed'].includes(item.status) && Number.isSafeInteger(item.price) && typeof item.product_name === 'string')
export const isReversalPreview = (body,id) => body?.operation?.id === id && typeof body.can_reverse === 'boolean'
  && Array.isArray(body.blockers) && body.blockers.every(item => typeof item === 'string')
  && (!body.can_reverse || body.blockers.length === 0)
  && Array.isArray(body.assets) && body.assets.every(item => typeof item.code === 'string' && Number.isSafeInteger(item.delta)
    && (item.before === null && item.after === null && !body.can_reverse || Number.isSafeInteger(item.before) && item.before >= 0
      && Number.isSafeInteger(item.after) && item.after === item.before + item.delta && (!body.can_reverse || item.after >= 0)))
  && ['badges_remove','badges_restore'].every(key => Array.isArray(body[key]) && body[key].every(item => typeof item.code === 'string' && Number.isSafeInteger(item.count) && item.count > 0))

export function useParentPage(props, endpoint, filters, validate = isParentPage) {
  const data = ref({items:[],total:0,has_more:false})
  const loading = ref(false), error = ref(''), ready = ref(false)
  let version = 0, alive = true
  const load = async (more = false) => {
    const current = ++version
    loading.value = true; error.value = ''; ready.value = false
    if (!more) data.value = {...data.value,items:[],has_more:false,total:0}
    try {
      const result = await props.api(`${endpoint}?${parentQuery(filters.value, more ? data.value.next_before_id : null)}`, {}, validate)
      if (!alive || current !== version) return
      data.value = {...result,items:more ? [...data.value.items,...result.items] : result.items}
      ready.value = true
    } catch (err) { if (alive && current === version) error.value = err.message }
    finally { if (alive && current === version) loading.value = false }
  }
  watch([filters, () => props.refreshVersion], () => load(), {immediate:true,deep:true})
  onBeforeUnmount(() => { alive = false; version++ })
  return {data, loading, error, ready, load, blocked:computed(() => props.disabled || loading.value || !ready.value)}
}
