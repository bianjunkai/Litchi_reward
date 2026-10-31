<script setup>
import { computed, ref, watch } from 'vue'
import SettlementForm from './SettlementForm.vue'
import ParentDialog from './ParentDialog.vue'
import { isReviewPage, useParentPage } from './parent.js'
import { formatMoney } from './reward-rules.js'
import { formatHistoryTime } from './backpack.js'
const props = defineProps({api:Function,perform:Function,disabled:Boolean,busy:Boolean,refreshVersion:Number,actionError:String,timezone:String,focusId:Number})
const emit = defineEmits(['clear-error'])
const status = ref('pending'), search = ref(''), from = ref(''), to = ref('')
const appliedSearch = ref('')
watch(() => props.focusId, id => { search.value = id ? `#${id}` : ''; appliedSearch.value = search.value }, {immediate:true})
const filters = computed(() => ({status:status.value,search:appliedSearch.value,from_date:from.value,to_date:to.value}))
const {data,loading,error,load,blocked} = useParentPage(props,'/api/parent/review',filters,isReviewPage)
const selection = ref(null)
const choose = (item,payload) => { emit('clear-error'); selection.value = {item,payload} }
const confirm = async () => {
  if (!selection.value || blocked.value) return
  const {item,payload} = selection.value
  if (await props.perform(`/api/parent/redemptions/${item.id}/${payload ? 'approve' : 'reject'}`,payload,'POST',payload ? '消费已确认，券已扣除' : '已拒绝申请，未扣券')) selection.value = null
  else await load()
}
const final = computed(() => {
  const p = selection.value?.payload
  return p ? {value:p.coupon_count*3990, topUp:Math.max(0,p.actual_amount_fen-p.coupon_count*3990), forfeit:Math.max(0,p.coupon_count*3990-p.actual_amount_fen)} : null
})
</script>
<template>
  <section class="panel parent-review" :aria-busy="loading">
    <div class="panel-heading"><h2>消费审批</h2><span>待处理 {{ data.counts?.pending ?? '—' }} 项</span></div>
    <p class="muted">当前兑换券 {{ data.coupon_balance ?? '—' }} 张。申请不占用余额，确认时才扣券。</p>
    <form class="parent-filters" @submit.prevent="appliedSearch = search.trim(); load()">
      <label>申请状态<select v-model="status"><option value="pending">待确认</option><option value="all">全部申请</option><option value="approved">已使用</option><option value="rejected">已拒绝</option><option value="reversed">已撤销</option></select></label>
      <label>礼物名称或申请编号<input v-model="search" maxlength="160" placeholder="名称或 #12" /></label>
      <label>申请开始日期<input v-model="from" type="date" /></label><label>申请结束日期<input v-model="to" type="date" /></label>
      <button class="secondary-button" :disabled="loading">查询／刷新</button>
    </form>
    <p v-if="error" class="inline-error" role="alert">{{ error }} <button @click="load()">重试</button></p>
    <p v-if="loading" role="status">正在加载申请…</p>
    <p v-else class="muted">匹配 {{ data.total }} 项 · 已加载 {{ data.items.length }} 项</p>
    <p v-if="!loading && !error && !data.items.length" class="empty">这里没有符合条件的申请。</p>
    <article v-for="item in data.items" :key="item.id" class="settlement-card">
      <div class="redemption-row"><span>{{ item.icon }} {{ item.product_name }}<small>#{{ item.id }} · {{ formatHistoryTime(item.requested_at,timezone) }} · 计划 {{ item.price }} 张券</small></span><em>{{ {pending:'待确认',approved:'已使用',rejected:'已拒绝',reversed:'已撤销'}[item.status] }}</em></div>
      <details v-if="item.status === 'pending'" class="parent-approval"><summary>填写消费金额并审批</summary>
        <SettlementForm :item="item" :disabled="blocked" :balance="data.coupon_balance" @approve="payload => choose(item,payload)" />
        <button class="reject" :disabled="blocked" @click="choose(item,null)">拒绝申请（不扣券）</button>
      </details>
      <template v-else-if="item.actual_amount_fen != null"><p>使用 {{ item.coupons_used }} 张券 · 实际消费 ¥{{ formatMoney(item.actual_amount_fen) }}</p><p class="muted">家长补差 ¥{{ formatMoney(item.parent_top_up_fen) }} · 不找零 ¥{{ formatMoney(item.forfeited_fen) }}<span v-if="item.settlement_note"> · {{ item.settlement_note }}</span></p><p v-if="item.status === 'reversed'" class="muted">账本扣券已撤销，不代表实际消费退款。</p></template>
      <p v-else-if="['approved','reversed'].includes(item.status)" class="muted">旧规则记录：保留原始扣券，当时未记录实际人民币金额。</p>
    </article>
    <button v-if="data.has_more" class="secondary-button" :disabled="loading" @click="load(true)">加载更多申请</button>
  </section>
  <ParentDialog :open="!!selection" :busy="busy" :title="selection?.payload ? '最后确认本次消费' : '确认拒绝申请'" @close="selection = null">
    <template v-if="selection"><p>{{ selection.item.icon }} {{ selection.item.product_name }} · #{{ selection.item.id }}</p>
      <template v-if="final"><dl class="parent-impact"><div><dt>扣除兑换券</dt><dd>{{ selection.payload.coupon_count }} 张 · ¥{{ formatMoney(final.value) }}</dd></div><div><dt>实际消费</dt><dd>¥{{ formatMoney(selection.payload.actual_amount_fen) }}</dd></div><div><dt>家长补差</dt><dd>¥{{ formatMoney(final.topUp) }}</dd></div><div><dt>不找零</dt><dd>¥{{ formatMoney(final.forfeit) }}</dd></div><div><dt>扣券后余额</dt><dd>{{ data.coupon_balance - selection.payload.coupon_count }} 张</dd></div></dl><p class="muted">确认仅登记家庭账本，不会代为付款；金额或用券数量需修改时，请返回。</p></template>
      <p v-else>申请将标记为已拒绝，不扣除兑换券，孩子可以重新申请。</p>
      <p v-if="actionError" role="alert" class="inline-error">{{ actionError }}</p>
      <button class="primary-button" :disabled="blocked || (selection.payload && data.coupon_balance < selection.payload.coupon_count)" @click="confirm">{{ selection.payload ? '确认扣券并登记消费' : '确认拒绝，不扣券' }}</button>
    </template>
  </ParentDialog>
</template>
