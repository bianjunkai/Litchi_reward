<script setup>
import { computed, nextTick, ref } from 'vue'
import PixelArt from '../PixelArt.vue'
import BadgeEmblem from '../BadgeEmblem.vue'
import RewardGuide from '../RewardGuide.vue'
import BackpackHistory from '../BackpackHistory.vue'
import CouponExchange from '../CouponExchange.vue'
import { backpackTabs, routeHash } from '../navigation.js'
import { badgeColors, formatMoney } from '../reward-rules.js'

const props = defineProps({ dashboard: Object, badges: Array, section: String, api: Function, refreshVersion: Number, offline: Boolean })
const badgeHistory = ref(null)
const emit = defineEmits(['navigate','refresh','notify'])
const availableCount = computed(() => props.dashboard.badge_progress.available)
const starAssets = computed(() => props.dashboard.assets.filter(asset => asset.code !== 'coupon'))
const starTotal = computed(() => props.dashboard.star_total ?? props.dashboard.progress.total_stars)
const badgeColorName = color => badgeColors.find(item => item.value === color)?.label || '其他颜色'
const showBadgeRecords = async id => {
  badgeHistory.value?.selectBadge(id)
  await nextTick()
  document.querySelector('[aria-label="徽章获得记录"]')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' })
}
</script>

<template>
  <section class="view backpack-view">
    <div class="page-title"><span class="eyebrow">PLAYER INVENTORY</span><h1>我的背包 🎒</h1><p>每一份努力，都好好收在这里。</p></div>
    <nav class="section-tabs" aria-label="背包分类"><a v-for="tab in backpackTabs" :key="tab.id" :href="routeHash('backpack', tab.id)" :aria-current="section === tab.id ? 'page' : undefined">{{ tab.label }}</a></nav>

    <template v-if="section === 'stars'">
      <div class="module-heading"><h2>我的星星袋</h2><span>{{ starTotal }} 枚可用星星</span></div>
      <div class="asset-grid backpack-assets"><article v-for="asset in starAssets" :key="asset.code" class="asset-card" :class="{inactive: !asset.active}" :style="{'--accent': asset.color}"><div class="asset-icon"><PixelArt kind="star" :size="32" :style="{'--pixel-accent': asset.color}" /></div><div><strong>{{ asset.balance }}</strong><span>{{ asset.name }}{{ asset.active ? '' : ' · 暂未启用' }}</span></div></article></div>
      <section class="progress-card"><div class="progress-copy"><span class="eyebrow">🟢 绿色星星 + 🔴 红色星星 → 生活徽章</span><h2>{{ !dashboard.progress.enabled ? '生活徽章暂未启用' : dashboard.progress.can_redeem ? '可以兑换生活徽章啦！' : `还差 ${Math.max(0, dashboard.progress.target - dashboard.progress.total_stars)} 颗绿／红星星` }}</h2><p>只计算整理和按时吃饭获得的绿色、红色星星；橙色学习星星不计入。</p></div><div class="star-progress"><div class="stars-row" aria-hidden="true"><span v-for="index in dashboard.progress.target" :key="index" :class="{filled: index <= dashboard.progress.current}">★</span></div><small>{{ dashboard.progress.current }} / {{ dashboard.progress.target }}</small></div></section>
      <section class="progress-card study-badge-progress"><div class="progress-copy"><span class="eyebrow">🟠 橙色学习星星 → 太阳花徽章</span><h2>{{ !dashboard.study_progress.enabled ? '太阳花徽章暂未启用' : dashboard.study_progress.can_redeem ? '可以兑换太阳花徽章啦！' : `还差 ${Math.max(0, dashboard.study_progress.target - dashboard.study_progress.total_stars)} 颗橙色星星` }}</h2><p>学习获得的橙色星星单独累计，集齐 5 颗兑换 1 枚太阳花学习徽章。</p></div><div class="star-progress"><div class="stars-row orange-stars" aria-hidden="true"><span v-for="index in dashboard.study_progress.target" :key="index" :class="{filled: index <= dashboard.study_progress.current}">★</span></div><small>{{ dashboard.study_progress.current }} / {{ dashboard.study_progress.target }}</small></div></section>
      <button class="secondary-button backpack-parent-action" @click="emit('navigate', 'parent', 'exchange')">请家长确认兑换 →</button>
      <BackpackHistory kind="stars" :api="api" :child-id="dashboard.child.id" :assets="dashboard.assets" :badges="badges" :time-zone="dashboard.family_timezone" :refresh-version="refreshVersion" :offline="offline" />
    </template>

    <template v-else-if="section === 'badges'">
      <div class="module-heading"><h2>徽章收藏室</h2></div>
      <p class="page-note">展示当前还可使用的徽章。换券后，已使用的徽章会收进下方历史徽章展柜。</p>
      <div class="badge-grid"><article v-for="badge in badges" :key="badge.id" class="badge-card" :class="{earned: badge.earned_count}" :style="{'--badge-color': badge.color}">
        <div class="badge-medal"><BadgeEmblem :code="badge.code" :color="badge.color" :size="44" /></div>
        <h2>{{ badge.name }}</h2><p>{{ badge.description }}</p>
        <div class="badge-count">当前可用 {{ badge.available_count }} 枚</div>
        <div v-if="badge.colors?.some(variant => variant.available_count > 0)" class="badge-color-collection" :aria-label="`${badge.name}可用颜色数量`"><span v-for="variant in badge.colors.filter(item => item.available_count > 0)" :key="variant.color" :title="`${badgeColorName(variant.color)}：当前可用 ${variant.available_count} 枚`"><BadgeEmblem :code="badge.code" :color="variant.color" :size="24" /><b>{{ badgeColorName(variant.color) }} × {{ variant.available_count }}</b></span></div>
        <p v-if="!badge.active">暂未启用，不参与兑换</p><button class="text-button" @click="showBadgeRecords(badge.id)">查看获得记录 →</button>
      </article></div>
      <section class="progress-card badge-coupon-progress"><div class="progress-copy"><span class="eyebrow">徽章 → 兑换券</span><h2>{{ availableCount >= 5 ? '可以兑换一张券啦！' : `还差 ${5 - availableCount} 枚可用徽章` }}</h2><p>任意 5 枚已启用、未兑换的徽章，换 1 张 ¥39.90 券。</p></div><div class="star-progress"><div class="badge-progress-icons" aria-hidden="true"><span v-for="index in 5" :key="index" :class="{filled: index <= availableCount}">🏅</span></div><small>{{ Math.min(availableCount, 5) }} / 5</small></div></section>
      <button class="secondary-button backpack-parent-action" @click="emit('navigate', 'backpack', 'coupons')">选择徽章，申请兑换券 →</button>
      <BackpackHistory ref="badgeHistory" kind="badges" :api="api" :child-id="dashboard.child.id" :assets="dashboard.assets" :badges="badges" :time-zone="dashboard.family_timezone" :refresh-version="refreshVersion" :offline="offline" />
    </template>

    <template v-else-if="section === 'coupons'">
      <section class="coupon-wallet panel"><PixelArt kind="ticket" :size="54" /><div><h2>我的兑换券</h2><strong>{{ dashboard.coupons.balance }} <small>张</small></strong><p>总面额 ¥{{ formatMoney(dashboard.coupons.total_value_fen) }}</p></div></section>
      <CouponExchange :dashboard="dashboard" :api="api" :offline="offline" :refresh-version="refreshVersion" @refresh="emit('refresh')" @notify="message => emit('notify',message)" />
      <section class="panel"><h2>慢慢存，换喜欢的礼物</h2><p class="page-note">每张 ¥39.90，可以累积；每次最多使用 5 张（¥199.50）。申请不会扣券，家长确认消费后才扣除。</p><button class="primary-button" @click="emit('navigate', 'shop')">去奖励商城 →</button></section>
      <details class="panel"><summary>兑换券怎么获得和使用？</summary><p class="page-note">任意 5 枚可用徽章换 1 张券。实际消费高于券总额，由家长决定是否补足；低于时不找零、不折现。</p><button class="text-button" @click="emit('navigate', 'backpack', 'badges')">查看徽章进度 →</button></details>
      <BackpackHistory kind="coupon" :api="api" :child-id="dashboard.child.id" :assets="dashboard.assets" :badges="badges" :time-zone="dashboard.family_timezone" :refresh-version="refreshVersion" :offline="offline" />
    </template>

    <template v-else><RewardGuide /><p class="page-note">所有奖励发放、资产兑换和消费都需要家长确认。完整记录和纠错功能在家长中心。</p></template>
  </section>
</template>
