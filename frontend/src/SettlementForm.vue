<script setup>
import { computed, ref, watch } from 'vue'
import { formatMoney, moneyToFen } from './reward-rules.js'

const props = defineProps({ item: Object, disabled: Boolean, balance: {type:Number,default:null} })
const emit = defineEmits(['approve'])
const count = ref(Math.min(5, Math.max(1, props.item.price)))
const amount = ref(props.item.quoted_amount_fen == null ? '' : formatMoney(props.item.quoted_amount_fen))
const approveTopUp = ref(false)
const note = ref('')
const actual = computed(() => moneyToFen(amount.value))
const value = computed(() => count.value * 3990)
const topUp = computed(() => actual.value == null ? 0 : Math.max(0, actual.value - value.value))
const forfeited = computed(() => actual.value == null ? 0 : Math.max(0, value.value - actual.value))
const insufficient = computed(() => props.balance != null && count.value > props.balance)
watch([amount,count], () => { approveTopUp.value = false })
const submit = () => {
  if (actual.value == null || props.disabled || insufficient.value || (topUp.value > 0 && !approveTopUp.value)) return
  emit('approve', { actual_amount_fen: actual.value, coupon_count: count.value, approve_top_up: approveTopUp.value, note: note.value })
}
</script>
<template>
  <p v-if="item.price < 1 || item.price > 5" class="inline-error">旧申请用券数量不在 1–5 张范围，请拒绝后重新申请。</p>
  <form v-else class="editor-form settlement-form" @submit.prevent="submit">
    <div class="settlement-inputs"><label>本次使用兑换券<select v-model="count" :disabled="disabled"><option v-for="number in 5" :key="number" :value="number">{{ number }} 张 · ¥{{ formatMoney(number * 3990) }}</option></select></label>
    <label>实际消费金额（元）<input v-model="amount" type="text" inputmode="decimal" placeholder="例如 39.90" :disabled="disabled" required /></label></div>
    <div class="settlement-preview" aria-live="polite"><span>券总额 <b>¥{{ formatMoney(value) }}</b></span><template v-if="actual != null"><span>实际消费 <b>¥{{ formatMoney(actual) }}</b></span><span v-if="topUp">家长需补 <b>¥{{ formatMoney(topUp) }}</b></span><span v-if="forfeited">不找零金额 <b>¥{{ formatMoney(forfeited) }}</b></span></template></div>
    <p v-if="amount && actual == null" class="inline-error">请输入有效金额，最多两位小数。</p>
    <p v-if="insufficient" class="inline-error">当前只有 {{ balance }} 张券，余额不足，不能确认本次消费。</p>
    <label v-if="topUp" class="checkbox-row"><input v-model="approveTopUp" type="checkbox" :disabled="disabled" />家长同意补足差额 ¥{{ formatMoney(topUp) }}</label>
    <p v-if="forfeited" class="muted">低于券总额的 ¥{{ formatMoney(forfeited) }} 不找零、不折现，也不返还为代币或券。</p>
    <label>消费说明（可选）<input v-model="note" maxlength="500" placeholder="例如：周六木马王国门票" :disabled="disabled" /></label>
    <button class="primary-button" :disabled="disabled || insufficient || actual == null || (topUp > 0 && !approveTopUp)">核对使用 {{ count }} 张券</button>
  </form>
</template>
