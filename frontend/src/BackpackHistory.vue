<script setup>
import { onUnmounted, ref, watch } from 'vue'
import PixelArt from './PixelArt.vue'
import BadgeEmblem from './BadgeEmblem.vue'
import { badgeColors, formatMoney } from './reward-rules.js'
import { badgeStatuses, formatHistoryTime, historyAction, historyStatus, isBackpackPage } from './backpack.js'

const props = defineProps({ api: Function, kind: String, childId: Number, assets: Array, badges: Array, timeZone: String, refreshVersion: Number, offline: Boolean })
const items = ref([])
const total = ref(0)
const nextCursor = ref(null)
const loading = ref(false)
const error = ref('')
const asset = ref('all')
const direction = ref('all')
const badge = ref('')
const color = ref('')
const status = ref('all')
let generation = 0

const load = async (reset = false) => {
  if (!reset && (loading.value || !nextCursor.value)) return
  const current = reset ? ++generation : generation
  if (reset) { items.value = []; total.value = 0; nextCursor.value = null }
  if (props.offline) { error.value = '连接尚未恢复，记录暂时无法刷新。'; loading.value = false; return }
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ child_id: String(props.childId), limit: '20' })
  if (!reset) params.set('before_id', String(nextCursor.value))
  if (props.kind === 'badges') {
    if (badge.value) params.set('badge_id', badge.value)
    if (color.value) params.set('color', color.value)
    params.set('status', status.value)
  } else {
    params.set('wallet', props.kind)
    params.set('asset_code', asset.value)
    params.set('direction', direction.value)
  }
  try {
    const data = await props.api('/api/backpack/' + (props.kind === 'badges' ? 'badges' : 'ledger') + '?' + params,
      {}, value => isBackpackPage(value, props.kind, props.childId))
    if (current !== generation) return
    items.value = reset ? data.items : [...items.value, ...data.items]
    total.value = data.total
    nextCursor.value = data.next_before_id
  } catch (err) { if (current === generation) error.value = err.message }
  finally { if (current === generation) loading.value = false }
}
const resetFilters = () => { asset.value = 'all'; direction.value = 'all'; badge.value = ''; color.value = ''; status.value = 'all' }
const selectBadge = id => { resetFilters(); badge.value = String(id) }
defineExpose({ selectBadge })
watch(() => [props.kind, props.childId, props.refreshVersion, props.offline, asset.value, direction.value, badge.value, color.value, status.value], () => load(true), { immediate: true })
onUnmounted(() => { generation++ })
const time = value => formatHistoryTime(value, props.timeZone)
</script>

<template>
  <section class="panel backpack-history" :aria-label="kind === 'badges' ? '徽章获得记录' : kind === 'coupon' ? '兑换券获得与使用记录' : '星星获得与使用记录'" :aria-busy="loading">
    <div class="module-heading"><h2>{{ kind === 'badges' ? '获得的回忆' : kind === 'coupon' ? '兑换券小账本' : '星星小账本' }}</h2><span v-if="!error">{{ loading && !items.length ? '正在读取…' : `共 ${total} 条` }}</span></div>
    <div v-if="kind === 'badges'" class="history-filters">
      <label>徽章类型<select v-model="badge"><option value="">全部徽章</option><option v-for="item in badges" :key="item.id" :value="String(item.id)">{{ item.name }}</option></select></label>
      <label>使用状态<select v-model="status"><option v-for="item in badgeStatuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
      <label>徽章颜色<select v-model="color"><option value="">全部颜色</option><option v-for="item in badgeColors" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
    </div>
    <div v-else class="history-filters">
      <label v-if="kind === 'stars'">星星颜色<select v-model="asset"><option value="all">全部颜色</option><option v-for="item in assets.filter(item => item.code !== 'coupon')" :key="item.code" :value="item.code">{{ item.name }}{{ item.active ? '' : '（暂未启用）' }}</option></select></label>
      <div class="history-directions" role="group" aria-label="收支筛选"><button v-for="item in [{value:'all',label:'全部'},{value:'in',label:'增加'},{value:'out',label:'减少'}]" :key="item.value" :aria-pressed="direction === item.value" @click="direction = item.value">{{ item.label }}</button></div>
    </div>
    <div v-if="error" class="history-error" role="alert"><p>记录暂时没有更新：{{ error }}</p><small v-if="items.length">下方保留已加载的记录。</small><button class="secondary-button" :disabled="loading || offline" @click="load(!items.length)">重试加载记录</button></div>
    <p v-if="loading && !items.length" class="empty" role="status">正在翻开你的小账本…</p>
    <div v-else-if="!error && !items.length" class="history-empty"><PixelArt :kind="kind === 'coupon' ? 'ticket' : kind === 'badges' ? 'mushroom' : 'star'" :size="38" /><p>{{ asset !== 'all' || direction !== 'all' || badge || color || status !== 'all' ? '没有符合条件的记录，试试其他筛选吧。' : '小账本还没有记录，下一次努力就会留下足迹！' }}</p><button v-if="asset !== 'all' || direction !== 'all' || badge || color || status !== 'all'" class="text-button" @click="resetFilters">查看全部记录 →</button></div>
    <article v-for="item in items" :key="item.id" class="history-entry" :class="{'entry-reversed': item.status === 'reversed'}">
      <div class="history-entry-heading"><div class="history-entry-title"><BadgeEmblem v-if="kind === 'badges'" :code="item.code" :color="item.color" :size="25" /><PixelArt v-else :kind="kind === 'coupon' ? 'ticket' : 'star'" :size="27" :style="{'--pixel-accent': item.color}" /><strong>{{ kind === 'badges' ? item.name : item.asset_name }}</strong></div><span v-if="kind !== 'badges'" class="history-delta" :class="{positive: item.delta > 0}">{{ item.delta > 0 ? '+' : '' }}{{ item.delta }} {{ kind === 'coupon' ? '张' : '枚' }}</span></div>
      <div class="history-tags"><span v-if="kind !== 'badges'">{{ historyAction(item) }}</span><span :class="{'history-corrected': item.status === 'reversed' || item.status === 'reversal'}">{{ historyStatus(item, kind) }}</span><span v-if="item.rule_version === 'legacy'">旧规则记录</span></div>
      <p class="history-reason">{{ item.reason || '历史记录未填写原因' }}</p>
      <small class="history-time">{{ time(kind === 'badges' ? item.earned_at : item.created_at) }}</small>
      <p v-if="kind !== 'badges'" class="history-balance">{{ item.balance_after === null ? '旧记录不完整，无法还原当时余额；当前余额不受影响。' : `该条记账后${kind === 'stars' ? item.asset_name : '兑换券'}余额：${item.balance_after} ${kind === 'coupon' ? '张' : '枚'}` }}</p>
      <p v-else-if="item.status === 'spent'" class="history-balance">已用于徽章换券{{ item.spent_at ? ` · ${time(item.spent_at)}` : '' }}，收藏仍保留。</p>
      <p v-else-if="item.status === 'disabled'" class="history-balance">徽章仍然保留，启用前不参与兑换。</p>
      <p v-else-if="item.status === 'reversed'" class="history-balance">家长已撤销本次获得，不计入累计和可用数量。</p>
      <details v-if="item.settlement" class="history-settlement"><summary>查看消费明细 · {{ item.settlement.product_name }}</summary><template v-if="item.settlement.actual_amount_fen != null"><p>使用 {{ item.settlement.coupons_used }} 张券 · 券总额 ¥{{ formatMoney(item.settlement.coupons_used * item.settlement.coupon_value_fen) }}</p><p>实际消费 ¥{{ formatMoney(item.settlement.actual_amount_fen) }}</p><p>家长补差 ¥{{ formatMoney(item.settlement.parent_top_up_fen) }} · 不找零 ¥{{ formatMoney(item.settlement.forfeited_fen) }}</p><p v-if="item.settlement.settlement_note">{{ item.settlement.settlement_note }}</p></template><p v-else>历史消费未记录实际金额，保留原始扣券，不按新规则重算。</p><p v-if="item.status === 'reversal' || item.status === 'reversed'">奖励账户操作已撤销，这不代表实际消费已经退款。</p></details>
    </article>
    <div class="history-pagination"><small v-if="items.length">已展示 {{ items.length }} 条 · 按记账顺序从新到旧</small><button v-if="nextCursor" class="secondary-button" :disabled="loading || offline" @click="load()">{{ loading ? '正在加载…' : '再看一些记录' }}</button><small v-else-if="items.length && !loading && !error">已经看到最早的记录啦</small></div>
    <p class="history-footnote">这里只查看记录；有疑问请家长在“记录与纠错”中处理。{{ kind === 'badges' ? '' : '撤销保留原记录，并另记返还或扣回。' }}</p>
  </section>
</template>
