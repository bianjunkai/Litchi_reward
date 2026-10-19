<script setup>
import { computed, onMounted, ref } from 'vue'
import { isList } from './api.js'
import ResourceEditor from './ResourceEditor.vue'
import RewardGuide from './RewardGuide.vue'
import SettlementForm from './SettlementForm.vue'
import { badgeColors, formatMoney, moneyToFen } from './reward-rules.js'
import { parentTabs, routeHash } from './navigation.js'

const props = defineProps({ api: Function, dashboard: Object, tasks: Array, offline: Boolean, section: { type: String, default: 'today' } })
const emit = defineEmits(['changed','notify','lock','navigate'])
const summary = ref({})
const redemptions = ref([])
const pendingRedemptions = computed(() => redemptions.value.filter(item => item.status === 'pending'))
const operations = ref([])
const ledger = ref([])
const products = ref([])
const managedTasks = ref([])
const badges = ref([])
const rules = ref({ badge_ratio: 5, badges_per_coupon: 5, coupon_value_fen: 3990, max_coupons_per_redemption: 5, family_timezone: 'Asia/Shanghai' })
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const adjustment = ref({ asset_code: 'study_star', delta: 1, reason: '' })
const lifeBadge = computed(() => badges.value.find(badge => badge.code === 'life' && badge.active))
const conversionColor = ref('#f0aa37')
const newPin = ref('')
const confirmPin = ref('')
const productEditor = ref(null)
const taskEditor = ref(null)
const badgeEditor = ref(null)
const disabled = computed(() => busy.value || loading.value || props.offline)
const availableBadges = computed(() => props.dashboard.badges.reduce((sum, badge) => sum + badge.available_count, 0))
const badgeOptions = computed(() => [{value:null,label:'发放星星代币（每项每天 1 枚）'}, ...badges.value.filter(b => ['sports','fire','royal'].includes(b.code)).map(b => ({value:b.id,label:`发放${b.name}${b.active ? '' : ' · 尚未启用'}`}))])
const assetOptions = computed(() => props.dashboard.assets.filter(a => ['study_star','tidy_star','meal_star'].includes(a.code)).map(a => ({value:a.code,label:a.name})))
const editableProducts = computed(() => products.value.map(product => ({...product,cash_price:product.cash_price_fen == null ? '' : formatMoney(product.cash_price_fen)})))
const productFields = [{key:'name',label:'消费内容／商品名称',required:true,maxLength:80},{key:'description',label:'双方认可的消费说明'}, {key:'icon',label:'图标',maxLength:20},{key:'price',label:'计划使用兑换券（1–5 张）',type:'number',max:5},{key:'cash_price',label:'参考消费金额（元，可留空）',inputmode:'decimal'},{key:'active',label:'上架',type:'checkbox'}]
const taskFields = computed(() => [{key:'name',label:'任务名称',required:true,maxLength:80},{key:'description',label:'完成条件'}, {key:'badge_id',label:'奖励类型',options:badgeOptions.value},{key:'asset_code',label:'代币事项',options:assetOptions.value,when:draft => !draft.badge_id},{key:'amount',label:'每次徽章数量',type:'number',max:99,when:draft => !!draft.badge_id},{key:'badge_color',label:'徽章颜色（只表示外观／等级）',options:[{value:null,label:'使用徽章默认颜色'},...badgeColors],when:draft => !!draft.badge_id},{key:'active',label:'启用',type:'checkbox'}])
const badgeFields = [{key:'code',label:'徽章类型标识',readOnly:true},{key:'name',label:'徽章名称',required:true,maxLength:80},{key:'description',label:'用途或获得条件说明'},{key:'icon',label:'图标',maxLength:20},{key:'color',label:'默认颜色（只表示外观／等级）',options:badgeColors},{key:'active',label:'启用，启用后可参与兑换',type:'checkbox'}]
const operationNames = { task:'获得奖励',manual:'数据纠错',stars_to_badge:'代币换生活徽章',badges_to_coupon:'徽章换券',redemption:'使用兑换券',reversal:'撤销记录' }

const load = async () => {
  loading.value = true
  try {
    const data = await Promise.all([
      props.api('/api/parent/summary'), props.api('/api/parent/redemptions',{},isList),
      props.api('/api/parent/operations',{},isList), props.api('/api/parent/ledger',{},isList),
      props.api('/api/parent/products',{},isList), props.api('/api/parent/tasks',{},isList),
      props.api('/api/parent/badges',{},isList), props.api('/api/parent/rules'),
    ])
    ;[summary.value,redemptions.value,operations.value,ledger.value,products.value,managedTasks.value,badges.value,rules.value] = data
    error.value = ''
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
const perform = async (url, payload, method='POST', message='已保存') => {
  if (disabled.value) return false
  busy.value = true
  try {
    await props.api(url, { method, ...(payload === undefined ? {} : {body:JSON.stringify(payload)}) })
    await load()
    emit('changed'); emit('notify', message)
    return true
  } catch (err) { error.value = err.message; return false }
  finally { busy.value = false }
}
const saveResource = async (type, item, editor) => {
  if (type === 'products') {
    const amount = item.cash_price?.trim?.() || String(item.cash_price ?? '').trim()
    const fen = amount === '' ? null : moneyToFen(amount)
    if (amount !== '' && fen == null) { error.value = '参考金额须为有效人民币金额，最多两位小数'; return }
    item.cash_price_fen = fen
  }
  if (type === 'tasks' && !item.badge_id) { item.amount = 1; item.badge_color = null }
  if (type === 'badges') item.threshold = 5
  if (await perform(`/api/parent/${type}${item.id ? `/${item.id}` : ''}`, item, item.id ? 'PUT' : 'POST')) editor?.close()
}
const reverse = item => {
  if (window.confirm(`撤销“${item.reason}”？系统会保留原操作并记录反向流水。`)) perform(`/api/parent/operations/${item.id}/reverse`,undefined,'POST','已撤销，历史记录已保留')
}
const downloadBackup = async () => {
  if (disabled.value) return
  busy.value = true
  try {
    const backup = await props.api('/api/parent/backup')
    const url = URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'}))
    const link = document.createElement('a'); link.href = url; link.download = `family-rewards-${new Date().toISOString().slice(0,10)}.json`; link.click()
    setTimeout(() => URL.revokeObjectURL(url),1000)
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
const restoreBackup = async event => {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || disabled.value) return
  if (file.size > 8000000) { error.value = '备份文件不能超过 8MB'; return }
  try {
    const backup = JSON.parse(await file.text())
    if (!window.confirm('恢复备份会替换当前家庭奖励数据。恢复前系统会自动保存当前数据备份。确定继续？')) return
    await perform('/api/parent/restore',backup,'POST','已恢复，恢复前数据已自动备份')
  } catch { error.value = '文件不是有效的 JSON 备份' }
}
const updatePin = async () => {
  if (!/^[0-9]{6,12}$/.test(newPin.value) || newPin.value !== confirmPin.value) { error.value = '请设置 6–12 位数字 PIN，两次输入须一致'; return }
  if (disabled.value) return
  busy.value = true
  try {
    await props.api('/api/parent/pin',{method:'POST',body:JSON.stringify({pin:newPin.value})})
    newPin.value = ''; confirmPin.value = ''; emit('lock'); emit('notify','PIN 已更换，请重新解锁')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
const localDate = value => new Date(value).toLocaleString('zh-CN',{timeZone:rules.value.family_timezone})
onMounted(load)
</script>

<template>
  <div class="page-title"><span class="eyebrow">PARENT CONTROL ROOM</span><h1>家长中心 ⚙️</h1><p>每天发奖励，按需做管理。返回孩子模式时会自动锁定。</p></div>
  <nav class="section-tabs parent-tabs" aria-label="家长管理导航"><a v-for="tab in parentTabs" :key="tab.id" :href="routeHash('parent', tab.id)" :aria-current="section === tab.id ? 'page' : undefined">{{ tab.label }}</a></nav>
  <div v-if="error" class="status-card error-card" role="alert"><p>{{ error }}</p><button class="secondary-button" @click="load" :disabled="busy || loading">重新加载控制台</button></div>
  <p v-if="loading" role="status">正在加载控制台…</p>
  <div v-show="section === 'today'" class="summary-grid"><div><strong>{{ summary.today_claims || 0 }}</strong><span>今日发放</span></div><div><strong>{{ summary.pending_redemptions || 0 }}</strong><span>待确认兑换</span></div><div><strong>{{ availableBadges }}</strong><span>可用徽章</span></div></div>
  <section v-show="section === 'today'" class="panel"><div class="panel-heading"><h2>今日任务</h2><span>家长发放</span></div><div v-for="task in tasks" :key="task.id" class="parent-task"><span>{{ task.badge_icon || task.asset_icon }} {{ task.name }}</span><button :disabled="disabled || task.claimed_today" @click="perform(`/api/tasks/${task.id}/claim?child_id=1`,undefined,'POST','奖励已发放')">{{ task.claimed_today ? '已发放' : `+${task.amount} ${task.badge_id ? '枚徽章' : '颗星星'}` }}</button></div></section>
  <section v-show="section === 'exchange'" class="panel"><h2>奖励兑换</h2><p class="muted">代币 {{ dashboard.progress.total_stars }} 枚 · 可参与兑换的徽章 {{ availableBadges }} 枚</p><p>5 枚橙／绿／红色代币可混合，只换 1 枚生活徽章。</p><form class="editor-form" @submit.prevent="perform('/api/parent/conversions/stars',{child_id:1,badge_id:lifeBadge?.id,color:conversionColor},'POST','获得 1 枚生活徽章！')"><label>生活徽章颜色<select v-model="conversionColor"><option v-for="color in badgeColors" :key="color.value" :value="color.value">{{ color.label }}</option></select></label><button class="primary-button" :disabled="disabled || !lifeBadge || dashboard.progress.total_stars < 5">5 枚代币 → 1 枚生活徽章</button></form><button class="secondary-button" :disabled="disabled || availableBadges < 5" @click="perform('/api/parent/conversions/coupon',{child_id:1},'POST','获得 1 张 ¥39.90 兑换券！')">5 枚可用徽章 → 1 张兑换券</button><p class="muted">任意类型、颜色可混合。体育及预留徽章通过家长设定的任务获得；未启用徽章不参与。</p></section>
  <section v-if="section === 'today'" class="panel parent-pending">
    <div class="panel-heading"><h2>待处理申请</h2><span>{{ pendingRedemptions.length }} 项</span></div>
    <p v-if="!pendingRedemptions.length" class="empty">暂时没有待处理申请。</p>
    <div v-for="item in pendingRedemptions" :key="item.id" class="redemption-row"><span>{{ item.icon }} {{ item.product_name }}<small>申请使用 {{ item.price }} 张券 · 尚未扣券</small></span><button class="secondary-button" @click="emit('navigate', 'exchange')">去确认</button></div>
    <button class="text-button" @click="emit('navigate', 'exchange')">前往兑换中心 →</button>
  </section>
  <section v-show="section === 'exchange'" class="panel"><div class="panel-heading"><h2>消费确认与记录</h2><span>确认后扣券 · 每次最多 5 张</span></div><div v-if="!redemptions.length" class="empty">还没有消费申请</div><article v-for="item in redemptions" :key="item.id" class="settlement-card"><div class="redemption-row"><span>{{ item.icon }} {{ item.product_name }}<small>{{ localDate(item.requested_at) }} · 申请使用 {{ item.price }} 张券</small></span><em>{{ {pending:'待确认',approved:'已使用',rejected:'已拒绝',reversed:'已撤销'}[item.status] }}</em></div><template v-if="item.status === 'pending'"><SettlementForm :item="item" :disabled="disabled" @approve="payload => perform(`/api/parent/redemptions/${item.id}/approve`,payload,'POST','消费已确认，券已扣除')" /><button class="reject" :disabled="disabled" @click="perform(`/api/parent/redemptions/${item.id}/reject`,undefined,'POST','已拒绝申请，未扣券')">拒绝申请</button></template><template v-else-if="item.actual_amount_fen != null"><p>使用 {{ item.coupons_used }} 张券（¥{{ formatMoney(item.coupons_used * item.coupon_value_fen) }}） · 实际消费 ¥{{ formatMoney(item.actual_amount_fen) }}</p><p class="muted">家长补差 ¥{{ formatMoney(item.parent_top_up_fen) }} · 不找零 ¥{{ formatMoney(item.forfeited_fen) }}<span v-if="item.settlement_note"> · {{ item.settlement_note }}</span></p></template><p v-else-if="item.status === 'approved' || item.status === 'reversed'" class="muted">历史旧规则记录，保留原始扣券；当时未记录人民币结算金额。</p></article></section>
  <details v-show="section === 'records'" class="panel"><summary>资产纠错</summary><form class="editor-form" @submit.prevent="perform('/api/parent/adjust',{child_id:1,...adjustment},'POST','资产已调整，流水已记录')"><label>资产<select v-model="adjustment.asset_code"><option v-for="asset in dashboard.assets.filter(a => a.active)" :key="asset.code" :value="asset.code">{{ asset.name }} · 当前 {{ asset.balance }}</option></select></label><label>变动数量（扣除填负数）<input v-model.number="adjustment.delta" type="number" min="-999" max="999" required /></label><label>调整原因<input v-model="adjustment.reason" maxlength="160" placeholder="例如：补记昨天的学习奖励" required /></label><button class="primary-button" :disabled="disabled">记录调整</button></form></details>
  <details v-show="section === 'records'" class="panel"><summary>发放与兑换记录 · 撤销</summary><div v-if="!operations.length" class="empty">还没有操作记录</div><div v-for="item in operations" :key="item.id" class="redemption-row"><span><small class="operation-kind">{{ operationNames[item.kind] || item.kind }}{{ item.rule_version === 'legacy' ? ' · 旧规则' : '' }}</small>{{ item.reason }}<small>#{{ item.id }} · {{ localDate(item.created_at) }}{{ item.reversal_of ? ` · 撤销原操作 #${item.reversal_of}` : '' }}</small></span><em v-if="item.reversed_at">已撤销</em><button v-else-if="!item.reversal_of" class="secondary-button" :disabled="disabled" @click="reverse(item)">撤销</button></div></details>
  <details v-show="section === 'records'" class="panel"><summary>资产流水</summary><div v-if="!ledger.length" class="empty">奖励从零开始，完成任务后就有流水啦。</div><div v-for="item in ledger" :key="item.id" class="redemption-row"><span>{{ item.icon }} {{ item.asset_name }} <b>{{ item.delta > 0 ? '+' : '' }}{{ item.delta }}</b><small>{{ item.reason }} · {{ localDate(item.created_at) }}</small></span><em>{{ item.operation_id ? `操作 #${item.operation_id}` : '历史补录' }}</em></div></details>
  <ResourceEditor v-show="section === 'products'" open ref="productEditor" title="商品管理" :items="editableProducts" :fields="productFields" :defaults="{name:'',description:'',icon:'🎁',price:1,cash_price:'',active:true}" :disabled="disabled" description="每张券 ¥39.90，每笔最多 5 张；可填写参考金额，最终由家长按实际消费结算。" @save="item => saveResource('products',item,productEditor)" />
  <ResourceEditor v-show="section === 'tasks'" open ref="taskEditor" title="任务管理" :items="managedTasks" :fields="taskFields" :defaults="{name:'',description:'',asset_code:'study_star',badge_id:null,badge_color:null,amount:1,active:true}" :disabled="disabled" description="日常代币每个事项每天最多 1 枚。徽章颜色仅表示外观或等级，获得条件写在任务说明中；生活徽章只通过代币兑换。" @save="item => saveResource('tasks',item,taskEditor)" />
  <ResourceEditor v-show="section === 'badges'" open ref="badgeEditor" title="徽章管理" :items="badges" :fields="badgeFields" :allow-create="false" :disabled="disabled" description="固定四种徽章，每种有绿、橙、红、金、银五个版本。预留徽章启用前，不参与发放或兑换。" @save="item => saveResource('badges',item,badgeEditor)" />
  <details v-show="section === 'settings'" class="panel"><summary>奖励规则与家庭时区</summary><RewardGuide /><p class="muted">兑换比例、券面额和单次上限按家庭约定固定；可以调整任务条件、颜色版本和预留徽章的启用状态。</p><form class="editor-form" @submit.prevent="perform('/api/parent/rules',rules,'PUT','家庭时区已更新')"><label>家庭时区<select v-model="rules.family_timezone"><option>Asia/Shanghai</option><option>Asia/Hong_Kong</option><option>Asia/Taipei</option><option>UTC</option></select></label><button class="primary-button" :disabled="disabled">保存时区</button></form></details>
  <details v-show="section === 'settings'" class="panel"><summary>备份与恢复</summary><p class="muted">导出包含奖励、规则与历史记录，不包含 PIN 或登录凭据。恢复前会自动保留当前数据。</p><button class="primary-button" :disabled="disabled" @click="downloadBackup">导出备份</button><label class="restore-label">选择 JSON 备份恢复<input type="file" accept="application/json,.json" :disabled="disabled" @change="restoreBackup" /></label></details>
  <details v-show="section === 'settings'" class="panel"><summary>更换家长 PIN</summary><form class="editor-form" @submit.prevent="updatePin"><label>新的 PIN<input v-model="newPin" type="password" inputmode="numeric" minlength="6" maxlength="12" autocomplete="new-password" required /></label><label>再次输入<input v-model="confirmPin" type="password" inputmode="numeric" minlength="6" maxlength="12" autocomplete="new-password" required /></label><button class="primary-button" :disabled="disabled">更换并锁定</button></form></details>
</template>
