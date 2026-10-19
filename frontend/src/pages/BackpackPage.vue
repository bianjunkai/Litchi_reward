<script setup>
import { computed } from 'vue'
import PixelArt from '../PixelArt.vue'
import BadgeEmblem from '../BadgeEmblem.vue'
import RewardGuide from '../RewardGuide.vue'
import { backpackTabs, routeHash } from '../navigation.js'
import { formatMoney } from '../reward-rules.js'

const props = defineProps({ dashboard: Object, badges: Array, history: Array, section: String })
const emit = defineEmits(['navigate'])
const earnedCount = computed(() => props.badges.reduce((sum, badge) => sum + badge.earned_count, 0))
const availableCount = computed(() => props.dashboard.badge_progress.available)
const starAssets = computed(() => props.dashboard.assets.filter(asset => asset.code !== 'coupon'))
const localDate = value => new Date(value).toLocaleString('zh-CN', { timeZone: props.dashboard.family_timezone || 'Asia/Shanghai' })
</script>

<template>
  <section class="view backpack-view">
    <div class="page-title"><span class="eyebrow">PLAYER INVENTORY</span><h1>我的背包 🎒</h1><p>每一份努力，都好好收在这里。</p></div>
    <nav class="section-tabs" aria-label="背包分类"><a v-for="tab in backpackTabs" :key="tab.id" :href="routeHash('backpack', tab.id)" :aria-current="section === tab.id ? 'page' : undefined">{{ tab.label }}</a></nav>

    <template v-if="section === 'stars'">
      <div class="module-heading"><h2>我的星星袋</h2><span>{{ dashboard.progress.total_stars }} 枚可用星星</span></div>
      <div class="asset-grid backpack-assets"><article v-for="asset in starAssets" :key="asset.code" class="asset-card" :class="{inactive: !asset.active}" :style="{'--accent': asset.color}"><div class="asset-icon"><PixelArt kind="star" :size="32" :style="{'--pixel-accent': asset.color}" /></div><div><strong>{{ asset.balance }}</strong><span>{{ asset.name }}{{ asset.active ? '' : ' · 暂未启用' }}</span></div></article></div>
      <section class="progress-card"><div class="progress-copy"><span class="eyebrow">星星 → 生活徽章</span><h2>{{ !dashboard.progress.enabled ? '生活徽章暂未启用' : dashboard.progress.can_redeem ? '可以兑换生活徽章啦！' : `还差 ${Math.max(0, 5 - dashboard.progress.total_stars)} 枚星星` }}</h2><p>橙、绿、红星星可以混色，5 枚只换 1 枚生活徽章。</p></div><div class="star-progress"><div class="stars-row" aria-hidden="true"><span v-for="index in 5" :key="index" :class="{filled: index <= dashboard.progress.current}">★</span></div><small>{{ dashboard.progress.current }} / 5</small></div></section>
      <button class="secondary-button backpack-parent-action" @click="emit('navigate', 'parent', 'exchange')">请家长确认兑换 →</button>
    </template>

    <template v-else-if="section === 'badges'">
      <div class="module-heading"><h2>徽章收藏室</h2><span>累计 {{ earnedCount }} · 可用 {{ availableCount }}</span></div>
      <p class="page-note">兑换不会抹去收藏。绿、橙、红、金、银只表示外观或等级。</p>
      <div class="badge-grid"><article v-for="badge in badges" :key="badge.id" class="badge-card" :class="{earned: badge.earned_count}" :style="{'--badge-color': badge.color}"><div class="badge-medal"><BadgeEmblem v-if="['sports','life','fire','royal'].includes(badge.code)" :code="badge.code" :color="badge.color" :size="44" /><span v-else>{{ badge.icon }}</span></div><h2>{{ badge.name }}</h2><p>{{ badge.description }}</p><div class="badge-count">累计 {{ badge.earned_count }} · 未兑换 {{ badge.unspent_count }}</div><p>{{ badge.active ? `可参与兑换 ${badge.available_count} 枚` : '暂未启用，不参与兑换' }}</p></article></div>
      <section class="progress-card badge-coupon-progress"><div class="progress-copy"><span class="eyebrow">徽章 → 兑换券</span><h2>{{ availableCount >= 5 ? '可以兑换一张券啦！' : `还差 ${5 - availableCount} 枚可用徽章` }}</h2><p>任意 5 枚已启用、未兑换的徽章，换 1 张 ¥39.90 券。</p></div><div class="star-progress"><div class="badge-progress-icons" aria-hidden="true"><span v-for="index in 5" :key="index" :class="{filled: index <= availableCount}">🏅</span></div><small>{{ Math.min(availableCount, 5) }} / 5</small></div></section>
      <button class="secondary-button backpack-parent-action" @click="emit('navigate', 'parent', 'exchange')">请家长确认兑换 →</button>
      <section class="panel badge-history"><h2>获得的回忆</h2><p v-if="!history.length" class="empty">完成冒险，点亮第一枚徽章吧！</p><div v-for="item in history" :key="item.id" class="redemption-row"><span><b :style="{color: item.color}"><BadgeEmblem :code="item.code" :color="item.color" :size="24" /> {{ item.name }}</b><small>{{ localDate(item.earned_at) }} · {{ item.reason }}</small></span><em>{{ item.reversed_at ? '已撤销' : item.spent_operation_id ? '已兑换' : item.active ? '可使用' : '尚未启用' }}</em></div></section>
    </template>

    <template v-else-if="section === 'coupons'">
      <section class="coupon-wallet panel"><PixelArt kind="ticket" :size="54" /><div><h2>我的兑换券</h2><strong>{{ dashboard.coupons.balance }} <small>张</small></strong><p>总面额 ¥{{ formatMoney(dashboard.coupons.total_value_fen) }}</p></div></section>
      <section class="panel"><h2>慢慢存，换喜欢的礼物</h2><p class="page-note">每张 ¥39.90，可以累积；每次最多使用 5 张（¥199.50）。申请不会扣券，家长确认消费后才扣除。</p><button class="primary-button" @click="emit('navigate', 'shop')">去奖励商城 →</button></section>
      <details class="panel"><summary>兑换券怎么获得和使用？</summary><p class="page-note">任意 5 枚可用徽章换 1 张券。实际消费高于券总额，由家长决定是否补足；低于时不找零、不折现。</p><button class="text-button" @click="emit('navigate', 'backpack', 'badges')">查看徽章进度 →</button></details>
    </template>

    <template v-else><RewardGuide /><p class="page-note">所有奖励发放、资产兑换和消费都需要家长确认。完整记录和纠错功能在家长中心。</p></template>
  </section>
</template>
