<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { isDashboard, isList } from './api.js'
import ResourceEditor from './ResourceEditor.vue'
import RewardManager from './RewardManager.vue'
import RewardGuide from './RewardGuide.vue'
import ParentReview from './ParentReview.vue'
import ParentRecords from './ParentRecords.vue'
import CouponExchange from './CouponExchange.vue'
import { badgeColors } from './reward-rules.js'
import { parentTabs, routeHash } from './navigation.js'
import { isReviewPage } from './parent.js'

const props = defineProps({ api: Function, dashboard: Object, tasks: Array, offline: Boolean, refreshVersion: Number, section: { type: String, default: 'today' } })
const emit = defineEmits(['changed','notify','lock','navigate','child-shop'])
const summary = ref({})
const pendingRedemptions = ref([])
const focusRequestId = ref(null)
const family = ref(props.dashboard)
const todayTasks = ref(props.tasks)
const taskFilter = ref('all')
const claimColors = ref({})
const visibleTasks = computed(() => todayTasks.value.filter(item => taskFilter.value === 'all' || (taskFilter.value === 'unclaimed' ? !item.claimed_today : item.claimed_today)))
const refreshTick = ref(0)
const ready = ref(false)
const loadError = ref('')
let loadVersion = 0, alive = true
onBeforeUnmount(() => { alive = false; loadVersion++ })
const products = ref([])
const managedTasks = ref([])
const badges = ref([])
const rules = ref({ badge_ratio: 5, badges_per_coupon: 5, coupon_value_fen: 3990, max_coupons_per_redemption: 5, family_timezone: 'Asia/Shanghai' })
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const conversionBadges = computed(() => badges.value.filter(badge => ['life','fire'].includes(badge.code) && badge.active))
const conversionBadgeId = ref(null)
const conversionBadge = computed(() => conversionBadges.value.find(badge => badge.id === conversionBadgeId.value) || conversionBadges.value[0])
const conversionProgress = computed(() => conversionBadge.value?.code === 'fire' ? family.value.study_progress : family.value.progress)
watch(conversionBadges, items => {
  if (!items.some(badge => badge.id === conversionBadgeId.value)) conversionBadgeId.value = items[0]?.id ?? null
}, {immediate:true})
const convertStars = () => conversionBadge.value && perform('/api/parent/conversions/stars',
  {child_id:1,badge_id:conversionBadge.value.id,color:conversionColor.value},'POST',`获得 1 枚${conversionBadge.value.name}！`)
const conversionColor = ref('#f0aa37')
const newPin = ref('')
const confirmPin = ref('')
const taskEditor = ref(null)
const badgeEditor = ref(null)
const disabled = computed(() => busy.value || loading.value || props.offline || !ready.value)
const availableBadges = computed(() => family.value.badges.reduce((sum, badge) => sum + badge.available_count, 0))
const badgeOptions = computed(() => [{value:null,label:'发放星星代币（每项每天 1 枚）'}, ...badges.value.filter(b => ['sports','royal'].includes(b.code)).map(b => ({value:b.id,label:`发放${b.name}${b.active ? '' : ' · 尚未启用'}`}))])
const assetOptions = computed(() => props.dashboard.assets.filter(a => ['study_star','tidy_star','meal_star'].includes(a.code)).map(a => ({value:a.code,label:a.name})))
const taskFields = computed(() => [{key:'name',label:'任务名称',required:true,maxLength:80},{key:'description',label:'完成条件'}, {key:'badge_id',label:'奖励类型',options:badgeOptions.value},{key:'asset_code',label:'代币事项',options:assetOptions.value,when:draft => !draft.badge_id},{key:'amount',label:'每次徽章数量',type:'number',max:99,when:draft => !!draft.badge_id},{key:'badge_color',label:'徽章颜色（只表示外观／等级）',options:[{value:null,label:'使用徽章默认颜色'},...badgeColors],when:draft => !!draft.badge_id},{key:'active',label:'启用',type:'checkbox'}])
const badgeFields = [{key:'code',label:'徽章类型标识',readOnly:true},{key:'name',label:'徽章名称',required:true,maxLength:80},{key:'description',label:'用途或获得条件说明'},{key:'icon',label:'图标',maxLength:20},{key:'color',label:'默认颜色（只表示外观／等级）',options:badgeColors},{key:'active',label:'启用，启用后可参与兑换',type:'checkbox'}]
const load = async () => {
  const version = ++loadVersion
  loading.value = true; ready.value = false
  try {
    const data = await Promise.all([
      props.api('/api/parent/summary'), props.api('/api/parent/review?status=pending&limit=5',{},isReviewPage),
      props.api('/api/parent/products',{},isList), props.api('/api/parent/tasks',{},isList),
      props.api('/api/parent/badges',{},isList), props.api('/api/parent/rules'),
      props.api('/api/dashboard/1',{},isDashboard), props.api('/api/tasks?child_id=1',{},isList),
    ])
    if (!alive || version !== loadVersion) return false
    ;[summary.value,,products.value,managedTasks.value,badges.value,rules.value,family.value,todayTasks.value] = data
    pendingRedemptions.value = data[1].items
    for (const task of todayTasks.value.filter(item => item.badge_id)) {
      claimColors.value[task.id] ??= task.badge_color || badges.value.find(badge => badge.id===task.badge_id)?.color || badgeColors[0].value
    }
    loadError.value = ''; ready.value = true; refreshTick.value++
    return true
  } catch (err) { if (alive && version === loadVersion) loadError.value = err.message; return false }
  finally { if (alive && version === loadVersion) loading.value = false }
}
const perform = async (url, payload, method='POST', message='已保存') => {
  if (disabled.value) return false
  busy.value = true; error.value = ''
  try {
    await props.api(url, { method, ...(payload === undefined ? {} : {body:JSON.stringify(payload)}) })
    const synced = await load()
    if (alive) {
      emit('changed')
      emit('notify', synced ? message : '操作已保存，但刷新失败；请重新加载核对，不要重复提交。')
    }
    return true
  } catch (err) {
    if (alive) {
      error.value = err.status ? err.message : '请求结果未确认，请重新加载记录核对，勿重复提交。'
      ready.value = false
    }
    return false
  } finally { busy.value = false }
}
const saveResource = async (type, item, editor) => {
  if (type === 'tasks' && !item.badge_id) { item.amount = 1; item.badge_color = null }
  if (type === 'badges') item.threshold = 5
  if (await perform(`/api/parent/${type}${item.id ? `/${item.id}` : ''}`, item, item.id ? 'PUT' : 'POST')) editor?.close()
}
const claimTask = task => perform(`/api/tasks/${task.id}/claim?child_id=1`,task.badge_id ? {color:claimColors.value[task.id]} : undefined,'POST','奖励已发放')
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
watch(() => props.refreshVersion, load, {immediate:true})
</script>

<template>
  <div class="parent-workspace" :aria-busy="loading">
  <div class="page-title"><span class="eyebrow">PARENT CONTROL ROOM</span><h1>家长中心 ⚙️</h1><p>每天发奖励，按需做管理。返回孩子模式时会自动锁定。</p></div>
  <nav class="section-tabs parent-tabs" aria-label="家长管理导航"><a v-for="tab in parentTabs" :key="tab.id" :href="routeHash('parent', tab.id)" :aria-current="section === tab.id ? 'page' : undefined" @click="focusRequestId = null">{{ tab.label }}</a></nav>
  <div v-if="error || loadError" class="status-card error-card" role="alert"><p>{{ error || loadError }}</p><p v-if="!ready">数据尚未核对，写操作已暂停。重新加载成功后再继续。</p><button class="secondary-button" @click="error = ''; load()" :disabled="busy || loading">重新加载控制台</button></div>
  <p v-if="loading" role="status">正在加载控制台…</p>
  <div v-show="section === 'today'" class="summary-grid parent-summary"><div><strong>{{ ready ? summary.today_claims : '—' }}</strong><span>今日发放</span></div><button @click="emit('navigate','exchange')"><strong>{{ ready ? summary.pending_redemptions + (summary.pending_coupon_requests || 0) : '—' }}</strong><span>待审批：换券与礼物 →</span></button><div><strong>{{ ready ? family.coupons.balance : '—' }}</strong><span>可用兑换券</span></div></div>
  <div v-show="section === 'today'" class="parent-quick-actions"><button class="secondary-button" @click="emit('navigate','products')">🎁 上架兑换奖励</button><span class="muted">门票、充值券、亲子活动都可以放进商城</span></div>
  <section v-show="section === 'today'" class="panel"><div class="panel-heading"><h2>今日任务</h2><label>显示<select v-model="taskFilter" aria-label="任务显示"><option value="all">全部任务</option><option value="unclaimed">待发放</option><option value="claimed">已发放</option></select></label></div><p v-if="!visibleTasks.length" class="empty">没有符合条件的任务。</p><div v-for="task in visibleTasks" :key="task.id" class="parent-task"><span>{{ task.badge_icon || task.asset_icon }} {{ task.name }}</span><div class="parent-task-actions"><label v-if="task.badge_id && !task.claimed_today">徽章颜色<select v-model="claimColors[task.id]" :aria-label="`${task.name}徽章颜色`" :disabled="disabled"><option v-for="color in badgeColors" :key="color.value" :value="color.value">{{ color.label }}</option></select></label><button :disabled="disabled || task.claimed_today" @click="claimTask(task)">{{ task.claimed_today ? '已发放' : `+${task.amount} ${task.badge_id ? '枚徽章' : '颗星星'}` }}</button></div></div></section>
  <CouponExchange v-if="section === 'exchange'" parent-mode :dashboard="family" :api="api" :perform="perform" :disabled="disabled" :busy="busy" :offline="offline" :refresh-version="refreshTick" />
  <details v-show="section === 'exchange'" class="panel parent-conversions"><summary>星星兑换学习／生活徽章</summary><p class="muted">可参与换券的徽章 {{ availableBadges }} 枚；兑换会扣除对应的 5 颗星星。</p><form class="editor-form" @submit.prevent="convertStars"><label>兑换路线<select v-model.number="conversionBadgeId" :disabled="!conversionBadges.length"><option v-for="badge in conversionBadges" :key="badge.id" :value="badge.id">{{ badge.code === 'fire' ? '太阳花学习徽章（橙色星星）' : '生活徽章（绿色／红色星星）' }}</option></select></label><p v-if="conversionBadge" class="muted">{{ conversionProgress?.total_stars || 0 }} / 5 颗指定颜色星星 · {{ conversionProgress?.can_redeem ? '可以兑换' : `还差 ${Math.max(0,5-(conversionProgress?.total_stars || 0))} 颗` }}</p><label>新徽章颜色<select v-model="conversionColor"><option v-for="color in badgeColors" :key="color.value" :value="color.value">{{ color.label }}</option></select></label><button class="primary-button" :disabled="disabled || !conversionBadge || !conversionProgress?.can_redeem">5 颗{{ conversionBadge?.code === 'fire' ? '橙色学习星星' : '绿／红星星' }} → 1 枚{{ conversionBadge?.name || '徽章' }}</button></form><p class="muted">太阳花学习徽章只能用橙色星星；生活徽章只能用绿色与红色星星，可混合。徽章换券请由孩子在背包中申请，再在上方审批。</p></details>
  <section v-if="section === 'today'" class="panel parent-pending">
    <p v-if="summary.pending_coupon_requests" class="coupon-waiting">有 {{ summary.pending_coupon_requests }} 项徽章换券申请，<button class="text-button" @click="emit('navigate','exchange')">前往审批 →</button></p>
    <div class="panel-heading"><h2>最近待处理申请</h2><span>{{ ready ? summary.pending_redemptions : '—' }} 项</span></div>
    <p v-if="!pendingRedemptions.length" class="empty">暂时没有待处理申请。</p>
    <div v-for="item in pendingRedemptions" :key="item.id" class="redemption-row"><span>{{ item.icon }} {{ item.product_name }}<small>申请 #{{ item.id }} · 使用 {{ item.price }} 张券 · 尚未扣券</small></span><button class="secondary-button" @click="focusRequestId = item.id; emit('navigate', 'exchange')">去审批</button></div>
    <button class="text-button" @click="emit('navigate', 'exchange')">前往兑换中心 →</button>
  </section>
  <ParentReview v-if="section === 'exchange'" :api="api" :perform="perform" :disabled="disabled" :busy="busy" :refresh-version="refreshTick" :action-error="error" :timezone="rules.family_timezone" :focus-id="focusRequestId" @clear-error="error = ''" />
  <ParentRecords v-if="section === 'records'" :api="api" :perform="perform" :dashboard="family" :disabled="disabled" :busy="busy" :refresh-version="refreshTick" :action-error="error" :timezone="rules.family_timezone" @clear-error="error = ''" />
  <RewardManager v-show="section === 'products'" :products="products" :disabled="disabled" :busy="busy" :perform="perform" :action-error="error" @clear-error="error = ''" @preview-shop="emit('child-shop')" />
  <ResourceEditor v-show="section === 'tasks'" open ref="taskEditor" title="任务管理" :items="managedTasks" :fields="taskFields" :defaults="{name:'',description:'',asset_code:'study_star',badge_id:null,badge_color:null,amount:1,active:true}" :disabled="disabled" description="日常代币每个事项每天最多 1 枚。体育徽章可以通过家长任务发放；太阳花学习徽章和生活徽章必须分别兑换对应星星。" @save="item => saveResource('tasks',item,taskEditor)" />
  <ResourceEditor v-show="section === 'badges'" open ref="badgeEditor" title="徽章管理" :items="badges" :fields="badgeFields" :allow-create="false" :disabled="disabled" description="固定四种徽章，每种有绿、橙、红、金、银五个版本。太阳花徽章由橙色学习星星兑换；生活徽章由绿／红星星兑换。" @save="item => saveResource('badges',item,badgeEditor)" />
  <details v-show="section === 'settings'" class="panel"><summary>奖励规则与家庭时区</summary><RewardGuide /><p class="muted">兑换比例、券面额和单次上限按家庭约定固定；可以调整任务条件、颜色版本和预留徽章的启用状态。</p><form class="editor-form" @submit.prevent="perform('/api/parent/rules',rules,'PUT','家庭时区已更新')"><label>家庭时区<select v-model="rules.family_timezone"><option>Asia/Shanghai</option><option>Asia/Hong_Kong</option><option>Asia/Taipei</option><option>UTC</option></select></label><button class="primary-button" :disabled="disabled">保存时区</button></form></details>
  <details v-show="section === 'settings'" class="panel"><summary>备份与恢复</summary><p class="muted">导出包含奖励、规则与历史记录，不包含 PIN 或登录凭据。恢复前会自动保留当前数据。</p><button class="primary-button" :disabled="disabled" @click="downloadBackup">导出备份</button><label class="restore-label">选择 JSON 备份恢复<input type="file" accept="application/json,.json" :disabled="disabled" @change="restoreBackup" /></label></details>
  <details v-show="section === 'settings'" class="panel"><summary>更换家长 PIN</summary><form class="editor-form" @submit.prevent="updatePin"><label>新的 PIN<input v-model="newPin" type="password" inputmode="numeric" minlength="6" maxlength="12" autocomplete="new-password" required /></label><label>再次输入<input v-model="confirmPin" type="password" inputmode="numeric" minlength="6" maxlength="12" autocomplete="new-password" required /></label><button class="primary-button" :disabled="disabled">更换并锁定</button></form></details>
  </div>
</template>
