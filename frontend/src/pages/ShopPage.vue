<script setup>
import { formatMoney } from '../reward-rules.js'
defineProps({ dashboard: Object, products: Array, busy: Boolean, offline: Boolean })
const emit = defineEmits(['request', 'navigate'])
</script>

<template>
  <section class="view shop-view">
    <div class="page-title"><span class="eyebrow">ITEM SHOP</span><h1>奖励商城 🎁</h1><p>挑一份喜欢的礼物，和家长一起兑换。</p></div>
    <div class="shop-wallet panel"><span>🎟️ 我有 <strong>{{ dashboard.coupons.balance }}</strong> 张券 · ¥{{ formatMoney(dashboard.coupons.total_value_fen) }}</span><button class="text-button" @click="emit('navigate', 'backpack', 'coupons')">查看兑换券 →</button></div>
    <details class="panel coupon-policy"><summary>亲子兑换说明</summary><p>每张 ¥39.90，每次最多 5 张（¥199.50）。申请不扣券，由家长按实际消费确认；不足由家长决定是否补差，低于券总额时不找零、不折现。</p></details>
    <p v-if="!products.length" class="panel empty">礼物正在准备中，请家长在商品管理中上架。</p>
    <div class="shop-grid"><article v-for="product in products" :key="product.id" class="product-card"><div class="product-icon">{{ product.icon }}</div><h2>{{ product.name }}</h2><p>{{ product.description }}</p><p v-if="product.cash_price_fen != null">参考价格 ¥{{ formatMoney(product.cash_price_fen) }}</p><div class="product-footer"><strong>🎟️ {{ product.price }} 张</strong><button :disabled="busy || offline" @click="emit('request', product)">申请兑换</button></div><small class="coupon-caption">券总额 ¥{{ formatMoney(product.price * 3990) }} · 家长确认后扣券</small></article></div>
  </section>
</template>
