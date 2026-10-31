<script setup>
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import PixelArt from '../PixelArt.vue'
import RewardArtwork from '../RewardArtwork.vue'
import { routeHash } from '../navigation.js'
import { formatHistoryTime } from '../backpack.js'
import { formatMoney } from '../reward-rules.js'
import { filterProducts, isShopRequests, productQuote, requestLabel, requestStatuses } from '../shop.js'

const props = defineProps({ dashboard: Object, products: Array, api: Function, section: String, refreshVersion: Number, offline: Boolean })
const emit = defineEmits(['navigate', 'notify', 'refresh'])
const items = ref([])
const counts = ref({ pending: 0, approved: 0, rejected: 0, reversed: 0 })
const pendingIds = ref([])
const ready = ref(false)
const total = ref(0)
const nextCursor = ref(null)
const loading = ref(false)
const error = ref('')
const status = ref('all')
const search = ref('')
const affordability = ref('all')
const selected = ref(null)
const dialog = ref(null)
const requestBusy = ref(false)
const requestError = ref('')
const lastRequestedId = ref(null)
let generation = 0
let alive = true

const visibleProducts = computed(() => filterProducts(props.products, search.value, affordability.value, props.dashboard.coupons.balance))
const allCount = computed(() => Object.values(counts.value).reduce((sum, count) => sum + count, 0))
const shortage = product => Math.max(0, product.price - props.dashboard.coupons.balance)
const time = value => formatHistoryTime(value, props.dashboard.family_timezone)
const loadRequests = async (reset = false) => {
  if (!reset && (loading.value || !nextCursor.value)) return
  const current = reset ? ++generation : generation
  if (reset) { items.value = []; total.value = 0; nextCursor.value = null }
  ready.value = false
  if (props.offline) { loading.value = false; error.value = '连接尚未恢复，请先刷新奖励数据。'; return }
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ child_id: String(props.dashboard.child.id), limit: '20', status: props.section === 'requests' ? status.value : 'all' })
  if (!reset) params.set('before_id', String(nextCursor.value))
  try {
    const data = await props.api('/api/shop/requests?' + params, {}, value => isShopRequests(value, props.dashboard.child.id))
    if (!alive || current !== generation) return
    items.value = reset ? data.items : [...items.value, ...data.items]
    total.value = data.total
    nextCursor.value = data.next_before_id
    counts.value = data.counts
    pendingIds.value = data.pending_product_ids
    ready.value = true
  } catch (err) { if (alive && current === generation) error.value = err.message }
  finally { if (alive && current === generation) loading.value = false }
}
watch(() => [props.section, props.section === 'requests' ? status.value : 'all', props.refreshVersion, props.offline, props.dashboard.child.id], () => loadRequests(true), { immediate: true })
onUnmounted(() => { alive = false; generation++ })

const openRequest = async product => {
  if (requestBusy.value || props.offline || !ready.value) return
  if (pendingIds.value.includes(product.id)) { emit('notify', '这个礼物已经在等家长确认啦'); return }
  selected.value = { ...product }
  requestError.value = ''
  await nextTick()
  dialog.value?.showModal()
}
const closeRequest = () => { if (!requestBusy.value) dialog.value?.close() }
const refreshCatalog = () => { closeRequest(); emit('refresh') }
const reapply = item => {
  const product = props.products.find(product => product.id === item.product_id)
  if (!product) { emit('notify', '礼物架可能已更新，请刷新后再试'); emit('refresh'); return }
  openRequest(product)
}
const submitRequest = async () => {
  if (!selected.value || requestBusy.value || props.offline || !ready.value) return
  requestBusy.value = true
  requestError.value = ''
  try {
    const result = await props.api('/api/redemptions', { method: 'POST', body: JSON.stringify({
      child_id: props.dashboard.child.id, product_id: selected.value.id, expected_product: productQuote(selected.value),
    }) }, value => value?.success === true && Number.isSafeInteger(value.id) && value.id > 0 && typeof value.message === 'string')
    if (!alive) return
    pendingIds.value = [...new Set([...pendingIds.value, selected.value.id])]
    lastRequestedId.value = result.id
    dialog.value?.close()
    emit('notify', result.message)
    const alreadyPending = status.value === 'pending'
    status.value = 'pending'
    if (props.section !== 'requests') emit('navigate', 'shop', 'requests')
    else if (alreadyPending) await loadRequests(true)
  } catch (err) { if (alive) requestError.value = err.message }
  finally { requestBusy.value = false }
}
</script>

<template>
  <section class="view shop-view" :aria-busy="loading">
    <div class="page-title"><span class="eyebrow">ITEM SHOP · 亲子奖励商店</span><h1>奖励商城 <PixelArt kind="mushroom" :size="30" /></h1><p>挑一份喜欢的礼物，和家长一起兑换。</p></div>
    <div class="shop-wallet panel"><div><PixelArt kind="ticket" :size="30" /><span>我有 <strong>{{ dashboard.coupons.balance }}</strong> 张券<small>总面额 ¥{{ formatMoney(dashboard.coupons.total_value_fen) }}</small></span></div><button class="text-button" @click="emit('navigate', 'backpack', 'coupons')">查看兑换券 →</button></div>
    <nav class="section-tabs" aria-label="商城分类"><a :href="routeHash('shop', 'catalog')" :aria-current="section === 'catalog' ? 'page' : undefined">🎁 礼物架</a><a :href="routeHash('shop', 'requests')" :aria-current="section === 'requests' ? 'page' : undefined">📮 我的申请 <span v-if="ready && counts.pending" class="shop-tab-count">{{ counts.pending }} 待确认</span></a></nav>
    <div v-if="error" class="history-error shop-error" role="alert"><p>申请记录暂时没有更新：{{ error }}</p><p>可以继续浏览礼物；同步成功后才能提交新申请。</p><button class="secondary-button" :disabled="loading || offline" @click="loadRequests(!items.length)">重试同步申请</button></div>

    <template v-if="section === 'catalog'">
      <div class="shop-search"><label>找礼物<input v-model="search" type="search" maxlength="80" placeholder="输入礼物名称" /></label><label>按兑换券筛选<select v-model="affordability"><option value="all">全部礼物</option><option value="enough">我的券够了</option><option value="need">还要再攒攒</option></select></label></div>
      <p class="shop-application-note">申请不扣券、不占用余额。券不够也可以先申请，攒够后再请家长确认。</p>
      <div v-if="!products.length" class="panel empty-state"><PixelArt kind="question" :size="42" /><h2>礼物正在准备中</h2><p>请家长在奖励上架中添加门票、充值券或其他奖励。</p><button class="secondary-button" @click="emit('navigate', 'parent', 'products')">请家长上架礼物</button></div>
      <div v-else-if="!visibleProducts.length" class="panel empty-state"><h2>暂时没有找到这份礼物</h2><p>试试其他名称，或者看看全部礼物。</p><button class="text-button" @click="search = ''; affordability = 'all'">看看全部礼物 →</button></div>
      <div class="shop-grid"><article v-for="product in visibleProducts" :key="product.id" class="product-card shop-product" :data-product-id="product.id"><RewardArtwork class="product-icon" :image="product.image_data" :icon="product.icon" :name="product.name" /><h2>{{ product.name }}</h2><p>{{ product.description }}</p><p v-if="product.cash_price_fen != null" class="shop-reference">参考金额 ¥{{ formatMoney(product.cash_price_fen) }}</p><div class="shop-product-price"><PixelArt kind="ticket" :size="20" /><strong>{{ product.price }} 张券</strong><small>券面额 ¥{{ formatMoney(product.price * 3990) }}</small></div><span class="shop-stock" :class="{enough: !shortage(product)}">{{ shortage(product) ? '还差 ' + shortage(product) + ' 张券，可以先申请' : '兑换券够了，请家长确认消费' }}</span><button class="shop-apply-button" :disabled="requestBusy || offline || !ready || pendingIds.includes(product.id)" @click="openRequest(product)">{{ ready && pendingIds.includes(product.id) ? '已申请 · 等家长确认' : !ready && loading ? '正在同步申请…' : '我想兑换' }}</button></article></div>
      <details class="panel coupon-policy shop-policy"><summary>亲子兑换说明</summary><p>每张 ¥39.90，每次最多 5 张（¥199.50）。申请时不扣券、不冻结余额；家长确认时重新检查余额，再按实际消费结算。高于券总额由家长决定是否补足，低于时不找零、不折现。</p></details>
    </template>

    <template v-else>
      <div class="shop-request-filters" role="group" aria-label="申请状态"><button v-for="item in requestStatuses" :key="item.value" :aria-pressed="status === item.value" @click="status = item.value">{{ item.label }}<span v-if="ready">{{ item.value === 'all' ? allCount : counts[item.value] }}</span></button></div>
      <p v-if="loading && !items.length" class="panel empty" role="status">正在查看你的礼物申请…</p>
      <section v-else-if="!error && !items.length" class="panel empty-state"><PixelArt kind="ticket" :size="42" /><h2>{{ status === 'all' ? '还没有礼物申请' : '暂时没有这个状态的申请' }}</h2><p>喜欢的礼物，可以和家长一起商量。</p><button v-if="status !== 'all'" class="text-button" @click="status = 'all'">查看全部申请 →</button><button class="secondary-button" @click="emit('navigate', 'shop', 'catalog')">去挑礼物 →</button></section>
      <div class="shop-request-list" :aria-busy="loading"><article v-for="item in items" :key="item.id" class="panel shop-request-card" :class="{'request-just-sent': item.id === lastRequestedId}" :data-request-id="item.id">
        <div class="shop-request-heading"><span class="shop-request-icon" aria-hidden="true">{{ item.icon }}</span><div><h2>{{ item.product_name }}</h2><small>申请时计划 {{ item.price }} 张券</small></div><span class="shop-request-status" :class="item.status">{{ requestLabel(item.status) }}</span></div>
        <div class="shop-request-times"><span>申请：{{ time(item.requested_at) }}</span><span v-if="item.approved_at">处理：{{ time(item.approved_at) }}</span><span v-if="item.reversed_at">撤销：{{ time(item.reversed_at) }}</span></div>
        <template v-if="item.status === 'pending'"><p class="shop-state-note">申请已送到家长，还没有扣券。确认时需要足够的兑换券，最终用券数量以家长结算为准。</p><p v-if="item.price > 5" class="inline-error shop-state-note">旧申请超过每次 5 张上限，请家长拒绝后，按当前礼物重新申请。</p><p v-if="item.coupon_value_fen != null" class="shop-snapshot">申请时券面额 ¥{{ formatMoney(item.price * item.coupon_value_fen) }}<span v-if="item.quoted_amount_fen != null"> · 参考金额 ¥{{ formatMoney(item.quoted_amount_fen) }}</span></p></template>
        <p v-else-if="item.status === 'rejected'" class="shop-state-note">家长暂时没有同意这次申请，没有扣券。可以一起商量，再选择合适的礼物。</p>
        <template v-else><p v-if="item.status === 'reversed'" class="shop-state-note">家长已撤销这笔奖励账户操作，原申请记录仍保留；这不代表实际消费已经退款。</p><p v-else class="shop-state-note">家长已确认消费，兑换券已按实际使用张数扣除。</p><details class="history-settlement"><summary>查看结算明细</summary><template v-if="item.actual_amount_fen != null"><p>使用 {{ item.coupons_used }} 张券 · 券总额 ¥{{ formatMoney(item.coupons_used * item.coupon_value_fen) }}</p><p>实际消费 ¥{{ formatMoney(item.actual_amount_fen) }}</p><p>家长补差 ¥{{ formatMoney(item.parent_top_up_fen) }} · 不找零 ¥{{ formatMoney(item.forfeited_fen) }}</p><p v-if="item.settlement_note">{{ item.settlement_note }}</p></template><p v-else>旧记录未保存完整结算明细，保留原始记录，不按新规则重算金额。</p></details></template>
        <p v-if="item.rule_version === 'legacy'" class="shop-snapshot">旧规则记录</p>
        <p v-if="!item.product_available" class="shop-snapshot">礼物已下架或暂不符合用券规则，历史申请仍保留。</p>
        <div class="shop-request-actions"><button v-if="item.can_reapply" class="secondary-button" :disabled="!ready || offline || requestBusy" @click="reapply(item)">再申请一次</button><button v-if="item.status === 'approved' || item.status === 'reversed'" class="text-button" @click="emit('navigate', 'backpack', 'coupons')">查看用券记录 →</button></div>
      </article></div>
      <div class="history-pagination"><small v-if="items.length">已展示 {{ items.length }} / {{ total }} 条 · 最近申请在前</small><button v-if="nextCursor" class="secondary-button" :disabled="loading || offline" @click="loadRequests()">{{ loading ? '正在加载…' : '再看一些申请' }}</button></div>
    </template>

    <dialog ref="dialog" class="shop-confirm-dialog" aria-labelledby="shop-confirm-heading" @cancel="requestBusy && $event.preventDefault()" @close="selected = null; requestError = ''">
      <form v-if="selected" @submit.prevent="submitRequest"><button type="button" class="shop-dialog-close" aria-label="关闭申请确认" :disabled="requestBusy" autofocus @click="closeRequest">×</button><RewardArtwork class="shop-dialog-artwork" :image="selected.image_data" :icon="selected.icon" :name="selected.name" /><h2 id="shop-confirm-heading">想要这份礼物吗？</h2><h3>{{ selected.name }}</h3><p>{{ selected.description }}</p><p class="shop-confirm-price">计划使用 {{ selected.price }} 张券 · ¥{{ formatMoney(selected.price * 3990) }}</p><p v-if="selected.cash_price_fen != null">参考金额 ¥{{ formatMoney(selected.cash_price_fen) }}</p><p v-if="shortage(selected)" class="shop-state-note">现在还差 {{ shortage(selected) }} 张券，可以先申请；攒够后再请家长确认。</p><p class="shop-state-note">这里只发送申请，不扣券、不冻结余额。最终消费和用券数量由家长确认。</p><p v-if="requestError" class="inline-error" role="alert">{{ requestError }}</p><div class="shop-dialog-actions"><button type="button" class="secondary-button" :disabled="requestBusy" @click="closeRequest">再想一想</button><button class="primary-button" :disabled="requestBusy || offline || !ready">{{ requestBusy ? '正在发送…' : '发送给家长' }}</button></div><button v-if="requestError" type="button" class="text-button" :disabled="requestBusy" @click="refreshCatalog">刷新礼物架后再试 →</button></form>
    </dialog>
  </section>
</template>
