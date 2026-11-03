<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import ParentDialog from './ParentDialog.vue'
import { adjustmentPreview, isReversalPreview, operationNames, signed, useParentPage } from './parent.js'
import { formatHistoryTime } from './backpack.js'
import { badgeColors } from './reward-rules.js'
const props = defineProps({api:Function,perform:Function,dashboard:Object,disabled:Boolean,busy:Boolean,refreshVersion:Number,actionError:String,timezone:String})
const emit = defineEmits(['clear-error'])
const view = ref('operations'), kind = ref('all'), state = ref('all'), asset = ref('all'), direction = ref('all')
const search = ref(''), appliedSearch = ref(''), from = ref(''), to = ref('')
const filters = computed(() => ({view:view.value,kind:kind.value,state:state.value,asset:asset.value,direction:direction.value,search:appliedSearch.value,from_date:from.value,to_date:to.value}))
const {data,loading,error,load,blocked} = useParentPage(props,'/api/parent/history',filters)
const draft = ref({asset_code:'study_star',delta:1,reason:''})
const adjustment = computed(() => adjustmentPreview(props.dashboard.assets,draft.value))
const badgeDraft = ref({badge_id:props.dashboard.badges[0]?.id ?? 1,color:badgeColors[0].value,delta:1,reason:''})
const selectedBadge = computed(() => props.dashboard.badges.find(item => item.id === badgeDraft.value.badge_id))
const selectedBadgeColor = computed(() => selectedBadge.value?.colors?.find(item => item.color === badgeDraft.value.color))
const badgeCount = computed(() => selectedBadgeColor.value?.available_count ?? 0)
const badgeAfter = computed(() => badgeCount.value + badgeDraft.value.delta)
const badgeAdjustmentValid = computed(() => !!selectedBadge.value && Number.isInteger(badgeDraft.value.delta)
  && badgeDraft.value.delta !== 0 && Math.abs(badgeDraft.value.delta) <= 999
  && !(badgeDraft.value.delta > 0 && ['life','fire'].includes(selectedBadge.value.code))
  && badgeAfter.value >= 0 && !!badgeDraft.value.reason.trim() && badgeDraft.value.reason.trim().length <= 160)
const selection = ref(null), preview = ref(null), previewError = ref(''), previewLoading = ref(false)
let alive = true, previewVersion = 0
onBeforeUnmount(() => { alive = false; previewVersion++ })
const showAdjustment = () => {
  if (blocked.value || !adjustment.value.valid) return
  emit('clear-error')
  selection.value = {type:'adjust',payload:{child_id:1,...draft.value,reason:draft.value.reason.trim(),expected_balance:adjustment.value.asset.balance},asset:{...adjustment.value.asset},after:adjustment.value.after}
}
const showBadgeAdjustment = () => {
  if (blocked.value || !badgeAdjustmentValid.value) return
  emit('clear-error')
  selection.value = {type:'badge-adjust',payload:{child_id:1,...badgeDraft.value,reason:badgeDraft.value.reason.trim(),expected_count:badgeCount.value},badge:{...selectedBadge.value},before:badgeCount.value,after:badgeAfter.value}
}
const showReversal = async item => {
  if (blocked.value || previewLoading.value) return
  emit('clear-error'); selection.value = {type:'reverse',item}; preview.value = null; previewError.value = ''; previewLoading.value = true
  const version = ++previewVersion
  try {
    const result = await props.api(`/api/parent/operations/${item.id}/preview`,{},data => isReversalPreview(data,item.id))
    if (alive && version === previewVersion) preview.value = result
  } catch (err) { if (alive && version === previewVersion) previewError.value = err.message }
  finally { if (alive && version === previewVersion) previewLoading.value = false }
}
const close = () => { selection.value = null; previewVersion++; previewLoading.value = false }
const confirm = async () => {
  if (blocked.value || !selection.value) return
  const item = selection.value
  if (item.type === 'reverse' && !preview.value?.can_reverse) return
  const success = item.type === 'adjust'
    ? await props.perform('/api/parent/adjust',item.payload,'POST','资产已调整，流水已保留')
    : item.type === 'badge-adjust'
      ? await props.perform('/api/parent/badge-adjust',item.payload,'POST','徽章已调整，记录已保留')
    : await props.perform(`/api/parent/operations/${item.item.id}/reverse`,undefined,'POST','已撤销，原记录与反向流水均已保留')
  if (success) { if (item.type === 'adjust') draft.value.reason = ''; if (item.type === 'badge-adjust') badgeDraft.value.reason = ''; close() }
  else { close(); await load() }
}
const lookup = id => { search.value = `#${id}`; appliedSearch.value = `#${id}`; kind.value = 'all'; state.value = 'all'; from.value = ''; to.value = ''; view.value = 'operations' }
</script>
<template>
  <details class="panel parent-adjust"><summary>资产补记／纠错</summary>
    <p class="muted">日常奖励请在工作台发放。这里用于补记或纠正星星、兑换券和徽章；生活徽章与太阳花学习徽章应通过各自指定颜色的 5 颗星星兑换。</p>
    <form class="editor-form" @submit.prevent="showAdjustment"><label>调整资产<select v-model="draft.asset_code" :disabled="blocked"><option v-for="item in dashboard.assets.filter(a => a.active)" :key="item.code" :value="item.code">{{ item.name }} · 当前 {{ item.balance }}</option></select></label>
      <label>变动数量（扣回填负数）<input v-model.number="draft.delta" type="number" min="-999" max="999" step="1" required :disabled="blocked" /></label>
      <label>调整原因<input v-model="draft.reason" required maxlength="160" placeholder="例如：补记昨天的学习奖励" :disabled="blocked" /></label>
      <p v-if="adjustment.asset" aria-live="polite">{{ adjustment.asset.name }}：{{ adjustment.asset.balance }} → {{ adjustment.after }}<span v-if="adjustment.after < 0" class="inline-error">（不能扣成负数）</span></p>
      <button class="primary-button" :disabled="blocked || !adjustment.valid">核对本次调整</button>
    </form>
    <form class="editor-form badge-adjust-form" @submit.prevent="showBadgeAdjustment"><h3>徽章补记／纠错</h3><p class="muted">生活徽章和太阳花徽章必须通过对应星星兑换；这里仅能扣回，不可直接补发。</p>
      <label>徽章类型<select v-model.number="badgeDraft.badge_id" :disabled="blocked"><option v-for="item in dashboard.badges" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
      <label>颜色<select v-model="badgeDraft.color" :disabled="blocked"><option v-for="color in badgeColors" :key="color.value" :value="color.value">{{ color.label }}</option></select></label>
      <label>变动数量（扣回填负数，可扣回 {{ badgeCount }} 枚）<input v-model.number="badgeDraft.delta" type="number" min="-999" max="999" step="1" required :disabled="blocked" /></label>
      <label>调整原因<input v-model="badgeDraft.reason" required maxlength="160" placeholder="例如：补记已确认获得的体育徽章" :disabled="blocked" /></label>
      <p aria-live="polite">{{ selectedBadge?.name }}（{{ badgeColors.find(color => color.value === badgeDraft.color)?.label }}）：未兑换 {{ badgeCount }} → {{ badgeAfter }}<span v-if="badgeAfter < 0" class="inline-error">（未兑换数量不足）</span></p>
      <button class="primary-button" :disabled="blocked || !badgeAdjustmentValid">核对本次徽章调整</button>
    </form>
  </details>
  <section class="panel parent-records" :aria-busy="loading">
    <div class="panel-heading"><h2>记录与纠错</h2><span>完整历史 · 每页 20 条</span></div>
    <div class="parent-view-tabs" role="group" aria-label="记录类型"><button :aria-pressed="view === 'operations'" @click="view = 'operations'">发放与兑换</button><button :aria-pressed="view === 'ledger'" @click="view = 'ledger'">资产流水</button></div>
    <form class="parent-filters" @submit.prevent="appliedSearch = search.trim(); load()">
      <template v-if="view === 'operations'"><label>操作类型<select v-model="kind"><option value="all">全部类型</option><option v-for="(name,key) in operationNames" :key="key" :value="key">{{ name }}</option></select></label><label>操作状态<select v-model="state"><option value="all">全部状态</option><option value="active">未撤销</option><option value="reversed">原操作已撤销</option><option value="reversal">反向纠错记录</option></select></label></template>
      <template v-else><label>资产<select v-model="asset" aria-label="流水资产"><option value="all">全部资产</option><option v-for="item in dashboard.assets" :key="item.code" :value="item.code">{{ item.name }}</option></select></label><label>收支方向<select v-model="direction"><option value="all">全部收支</option><option value="in">获得／返还</option><option value="out">使用／扣回</option></select></label></template>
      <label>原因或操作编号<input v-model="search" maxlength="160" placeholder="原因或 #12" /></label><label>开始日期<input v-model="from" type="date" /></label><label>结束日期<input v-model="to" type="date" /></label>
      <button class="secondary-button" :disabled="loading">查询／刷新</button>
    </form>
    <p class="muted">日期按家庭时区 {{ timezone }}，包含开始和结束当天。原记录不会因撤销被删除。</p>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button @click="load()">重试</button></p><p v-if="loading" role="status">正在加载记录…</p>
    <p v-else class="muted">匹配 {{ data.total }} 条 · 已加载 {{ data.items.length }} 条</p><p v-if="!loading && !error && !data.items.length" class="empty">没有符合条件的记录。</p>
    <article v-for="item in data.items" :key="`${view}-${item.id}`" class="parent-history-card">
      <div class="redemption-row"><span><small>{{ view === 'operations' ? operationNames[item.kind] || item.kind : `${item.icon} ${item.asset_name} ${signed(item.delta)}` }}{{ item.rule_version === 'legacy' ? ' · 旧规则' : '' }}</small>{{ item.reason }}<small>{{ view === 'operations' ? '操作' : '流水' }} #{{ item.id }} · {{ formatHistoryTime(item.created_at,timezone) }}</small></span><em v-if="item.reversed_at">原操作已撤销</em><em v-else-if="item.reversal_of">反向记录</em></div>
      <div v-if="view === 'operations'" class="parent-change-chips"><span v-for="change in item.asset_changes" :key="change.code">{{ change.icon }} {{ change.name }} {{ signed(change.delta) }}</span></div>
      <div v-if="view === 'operations' && item.badge_changes?.length" class="parent-change-chips"><span v-for="change in item.badge_changes" :key="`${change.code}-${change.color}`"><i class="badge-color-dot" :style="{background:change.color}"></i>{{ change.name }} {{ signed(change.delta) }}</span></div>
      <p v-if="item.reversal_of" class="muted">对应原操作 #{{ item.reversal_of }}</p>
      <button v-if="view === 'operations' && !item.reversed_at && !item.reversal_of" class="secondary-button" :disabled="blocked || previewLoading" @click="showReversal(item)">查看撤销影响</button>
      <button v-if="view === 'ledger' && item.operation_id" class="text-button" @click="lookup(item.operation_id)">查看原操作 #{{ item.operation_id }} →</button>
      <p v-if="view === 'ledger' && !item.operation_id" class="muted">历史补录，没有关联操作。</p>
    </article>
    <button v-if="data.has_more" class="secondary-button" :disabled="loading" @click="load(true)">加载更多记录</button>
  </section>
  <ParentDialog :open="!!selection" :busy="busy" :title="selection?.type === 'adjust' ? '确认资产调整' : selection?.type === 'badge-adjust' ? '确认徽章调整' : '撤销影响预览'" @close="close">
    <template v-if="selection?.type === 'adjust'"><p>{{ selection.asset.name }}：{{ selection.asset.balance }} → <strong>{{ selection.after }}</strong>（{{ signed(selection.payload.delta) }}）</p><p>原因：{{ selection.payload.reason }}</p><p class="muted">系统会核对余额，并保留调整流水；余额变化时需重新确认。</p><button class="primary-button" :disabled="blocked" @click="confirm">确认调整并记账</button></template>
    <template v-else-if="selection?.type === 'badge-adjust'"><p>{{ selection.badge.name }} · {{ badgeColors.find(color => color.value === selection.payload.color)?.label }}：未兑换 {{ selection.before }} → <strong>{{ selection.after }}</strong>（{{ signed(selection.payload.delta) }}）</p><p>原因：{{ selection.payload.reason }}</p><p class="muted">调整会进入操作记录；新增徽章和扣回徽章都可以从记录页撤销。</p><button class="primary-button" :disabled="blocked" @click="confirm">确认徽章调整并记账</button></template>
    <template v-else-if="selection"><p>#{{ selection.item.id }} · {{ selection.item.reason }}</p><p v-if="previewLoading" role="status">正在核对余额与依赖关系…</p><p v-if="previewError" class="inline-error" role="alert">{{ previewError }}</p>
      <template v-if="preview"><dl class="parent-impact"><div v-for="item in preview.assets" :key="item.code"><dt>{{ item.icon }} {{ item.name }}</dt><dd>{{ item.before }} → {{ item.after }}（{{ signed(item.delta) }}）</dd></div></dl>
        <p v-for="item in preview.badges_remove" :key="`remove-${item.code}-${item.color}`">扣回 {{ item.count }} 枚{{ item.name }} <span class="badge-color-dot" :style="{background:item.color}"></span></p>
        <p v-for="item in preview.badges_restore" :key="`restore-${item.code}-${item.color}`">恢复 {{ item.count }} 枚未兑换{{ item.name }} <span class="badge-color-dot" :style="{background:item.color}"></span></p>
        <p v-for="message in preview.blockers" :key="message" class="inline-error" role="alert">{{ message }}</p>
        <p class="muted">只纠正家庭账本，不会退款或撤销现实消费。确认时会再次核对，原记录和反向流水均保留。</p>
        <button class="primary-button" :disabled="blocked || !preview.can_reverse" @click="confirm">确认撤销并保留流水</button>
      </template>
    </template>
    <p v-if="actionError" class="inline-error" role="alert">{{ actionError }}</p>
  </ParentDialog>
</template>
