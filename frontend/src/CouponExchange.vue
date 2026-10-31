<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import BadgeEmblem from './BadgeEmblem.vue'
import ParentDialog from './ParentDialog.vue'
import { formatHistoryTime } from './backpack.js'
import { colorName, couponBadgeChoices, couponRequestStates, couponSelection, isCouponRequestPage } from './coupon-exchange.js'

const props = defineProps({dashboard:Object,api:Function,perform:Function,parentMode:Boolean,disabled:Boolean,busy:Boolean,offline:Boolean,refreshVersion:Number})
const emit = defineEmits(['refresh','notify'])
const counts = ref({}), status = ref(props.parentMode ? 'pending' : 'all')
const data = ref({items:[],total:0,has_more:false,next_before_id:null,pending_count:0})
const loading = ref(false), ready = ref(false), sending = ref(false), error = ref(''), actionError = ref(''), selection = ref(null)
const choices = computed(() => couponBadgeChoices(props.dashboard.badges))
watch(choices, current => {
  const keys = new Set(current.map(item => item.key))
  for (const key of Object.keys(counts.value)) if (!keys.has(key)) delete counts.value[key]
})
const selected = computed(() => couponSelection(choices.value,counts.value))
const blocked = computed(() => props.disabled || props.busy || props.offline || loading.value || sending.value || !ready.value)
let version = 0, alive = true
const load = async (more=false) => {
  if (props.offline) { ready.value=false; error.value='请先恢复连接，再查看换券申请。'; return }
  const generation = ++version
  loading.value=true; ready.value=false; error.value=''
  const query = new URLSearchParams({child_id:String(props.dashboard.child.id),status:status.value,limit:'20'})
  if (more && data.value.next_before_id) query.set('before_id',String(data.value.next_before_id))
  try {
    const result = await props.api(`${props.parentMode ? '/api/parent' : '/api'}/coupon-requests?${query}`,{},isCouponRequestPage)
    if (!alive || generation !== version) return
    const updated = !props.parentMode && result.items.some(item => data.value.items.some(old => old.id===item.id && old.status==='pending' && item.status!=='pending'))
    data.value={...result,items:more ? [...data.value.items,...result.items] : result.items}; ready.value=true
    if (updated) { emit('refresh'); emit('notify','换券申请已更新，正在刷新背包。') }
  } catch (err) { if (alive && generation===version) error.value=err.message }
  finally { if (alive && generation===version) loading.value=false }
}
watch(() => [props.refreshVersion,props.offline,props.dashboard.child.id,status.value], () => load(), {immediate:true})
const poll = setInterval(() => {
  if (document.visibilityState==='visible' && !loading.value && !sending.value && !props.busy
    && (props.parentMode && status.value==='pending' || !props.parentMode && data.value.pending_count > 0)) void load()
},15000)
onBeforeUnmount(() => { alive=false; version++; clearInterval(poll) })
const chooseRequest = () => {
  if (!blocked.value && selected.value.valid && !data.value.pending_count) selection.value={action:'request',selections:selected.value.selections.map(item => ({...item}))}
}
const chooseReview = (item,action) => { if (!blocked.value) selection.value={action,item,selections:item.selections} }
const confirm = async () => {
  if (blocked.value || !selection.value) return
  const current = selection.value
  actionError.value=''
  if (props.parentMode) {
    if (current.action==='approve' && !data.value.items.find(item => item.id===current.item.id)?.can_approve) return
    const ok = await props.perform(`/api/parent/coupon-requests/${current.item.id}/${current.action}`,undefined,'POST',
      current.action==='approve' ? '换券已批准：扣除所选 5 枚徽章，增加 1 张兑换券' : '换券申请已拒绝，未扣除徽章')
    selection.value=null
    if (!ok) await load()
    return
  }
  sending.value=true
  try {
    const result = await props.api('/api/coupon-requests',{method:'POST',body:JSON.stringify({child_id:props.dashboard.child.id,selections:current.selections})},
      value => value?.success===true && Number.isSafeInteger(value.id) && typeof value.message==='string')
    if (!alive) return
    selection.value=null; counts.value={}; emit('notify',result.message); await load(); emit('refresh')
  } catch (err) {
    if (!alive) return
    actionError.value=err.status ? err.message : '提交结果尚未确认，请刷新申请记录核对，勿重复提交。'
    selection.value=null; await load(); emit('refresh')
  } finally { if (alive) sending.value=false }
}
const close = () => { if (!sending.value && !props.busy) selection.value=null }
</script>

<template>
  <section class="panel coupon-exchange" :aria-busy="loading || sending">
    <div class="panel-heading"><h2>{{ parentMode ? '徽章换券审批' : '申请兑换券' }}</h2><span>5 枚徽章 → 1 张 ¥39.90 券</span></div>
    <p class="muted">孩子选择 5 枚已启用、未兑换的徽章申请。家长同意后才扣除这些徽章，兑换券可以继续积攒。</p>
    <form v-if="!parentMode && !data.pending_count" class="editor-form" @submit.prevent="chooseRequest">
      <p v-if="!choices.length" class="empty">还没有可用徽章，先完成冒险吧。</p>
      <label v-for="choice in choices" :key="choice.key" class="coupon-badge-choice"><span><BadgeEmblem :code="choice.code" :color="choice.color" :size="26" />{{ colorName(choice.color) }}{{ choice.name }}<small>可用 {{ choice.available }} 枚</small></span><input v-model.number="counts[choice.key]" type="number" min="0" :max="Math.min(5,choice.available)" step="1" :aria-label="`选择${colorName(choice.color)}${choice.name}数量`" :disabled="blocked" placeholder="0" /></label>
      <p aria-live="polite">已选 {{ selected.total }} / 5 枚徽章</p>
      <button class="primary-button" :disabled="blocked || !selected.valid">请家长审批换券</button>
    </form>
    <p v-if="!parentMode && data.pending_count" class="coupon-waiting" role="status">申请正在等待家长审批。此时徽章尚未扣除，也没有增加兑换券。</p>
    <label v-if="parentMode" class="coupon-request-filter">显示<select v-model="status" :disabled="sending || busy"><option value="pending">待审批</option><option value="all">全部申请</option><option value="approved">已换券</option><option value="rejected">未同意</option><option value="reversed">已撤销</option></select></label>
    <p v-if="error || actionError" class="inline-error" role="alert">{{ actionError || error }}</p>
    <button class="text-button" :disabled="loading || sending || busy || offline" @click="actionError=''; load()">刷新换券申请</button>
    <h3>{{ parentMode ? `匹配 ${data.total} 项` : '我的换券申请' }}</h3>
    <p v-if="!loading && !error && !data.items.length" class="empty">暂时没有换券申请。</p>
    <article v-for="item in data.items" :key="item.id" class="coupon-request-card">
      <div class="module-heading"><strong>换券申请 #{{ item.id }}</strong><span>{{ couponRequestStates[item.status] }}</span></div>
      <div class="parent-change-chips"><span v-for="choice in item.selections" :key="`${choice.badge_id}-${choice.color}`"><BadgeEmblem :code="choice.code" :color="choice.color" :size="22" />{{ colorName(choice.color) }}{{ choice.name }} × {{ choice.count }}</span></div>
      <small>{{ formatHistoryTime(item.requested_at,dashboard.family_timezone) }}</small>
      <p v-if="item.status==='approved'">已扣除以上 5 枚徽章，获得 1 张兑换券；历史收藏仍保留。</p>
      <p v-else-if="item.status==='rejected'">未扣除徽章，可以重新选择后申请。</p>
      <p v-else-if="item.status==='reversed'">本次换券已撤销，兑换券已扣回，所选徽章已返还。</p>
      <p v-else-if="!item.can_approve" class="inline-error">所选徽章已使用、已撤销或已停用。请家长拒绝后重新申请。</p>
      <div v-if="parentMode && item.status==='pending'" class="form-actions"><button class="primary-button" :disabled="blocked || !item.can_approve" @click="chooseReview(item,'approve')">审批换券</button><button class="secondary-button" :disabled="blocked" @click="chooseReview(item,'reject')">拒绝申请</button></div>
    </article>
    <button v-if="data.has_more" class="secondary-button" :disabled="blocked" @click="load(true)">查看更多换券申请</button>
  </section>
  <ParentDialog :open="!!selection" :busy="sending || busy" :title="selection?.action==='request' ? '确认申请兑换券' : selection?.action==='approve' ? '确认扣章并换券' : '确认拒绝换券申请'" @close="close">
    <template v-if="selection">
      <p v-if="selection.action==='request'">提交后等待家长审批，现在不会扣除徽章。</p>
      <p v-else-if="selection.action==='approve'">将扣除孩子所选的 5 枚徽章，增加 1 张 ¥39.90 兑换券。</p>
      <p v-else>拒绝本次换券申请，不扣除徽章。</p>
      <p v-for="choice in selection.selections" :key="`${choice.badge_id}-${choice.color}`">{{ colorName(choice.color) }}{{ dashboard.badges.find(badge => badge.id===choice.badge_id)?.name }} × {{ choice.count }}</p>
      <button class="primary-button" :disabled="blocked || (selection.action==='request' && !selected.valid) || (selection.action==='approve' && !data.items.find(item => item.id===selection.item.id)?.can_approve)" @click="confirm">{{ selection.action==='request' ? '确认提交，等待审批' : selection.action==='approve' ? '确认扣除徽章并发券' : '确认拒绝，不扣徽章' }}</button>
    </template>
  </ParentDialog>
</template>
