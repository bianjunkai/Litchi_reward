<script setup>
import { computed } from 'vue'
import PixelArt from '../PixelArt.vue'
import BadgeEmblem from '../BadgeEmblem.vue'
import HeroWorld from '../HeroWorld.vue'
import { homeChallenges, homeInventory } from '../page-models.js'

const props = defineProps({ dashboard: Object, tasks: Array, badges: Array })
const emit = defineEmits(['navigate'])
const inventory = computed(() => homeInventory(props.dashboard, props.badges))
const challenges = computed(() => homeChallenges(props.tasks, props.badges))
const available = computed(() => props.dashboard.badge_progress.available)
</script>

<template>
  <section class="view home-view compact-home" aria-label="城堡首页">
    <section class="sky-banner mario-banner compact-banner" aria-labelledby="castle-heading">
      <div class="world-hud"><span><PixelArt kind="mario" :size="18" /> SUPER FAMILY</span><span>WORLD 1–1</span></div>
      <div class="hero-copy"><span class="world-label">{{ dashboard.child.name }}的成长世界</span><h1 id="castle-heading">我的奖励城堡</h1><p>每天进步一点点，一起闯关吧！</p><button class="adventure-button" @click="emit('navigate', 'adventures', 'all')">开始今天的冒险 <span>→</span></button></div>
      <HeroWorld />
    </section>

    <section class="home-module" aria-labelledby="inventory-heading">
      <div class="module-heading"><h2 id="inventory-heading">🎒 我的奖励</h2><button class="text-button" @click="emit('navigate', 'backpack')">打开背包 →</button></div>
      <div class="inventory-overview"><button v-for="item in inventory" :key="item.id" :class="{inactive: !item.active}" :style="{'--accent': item.color}" @click="emit('navigate', 'backpack', item.section)">
        <PixelArt v-if="item.icon" :kind="item.icon" :size="28" :style="{'--pixel-accent': item.color}" /><BadgeEmblem v-else :code="item.id" :color="item.color" :size="26" />
        <strong>{{ item.count }}</strong><span>{{ item.label }}</span><small v-if="!item.active">暂未启用</small>
      </button></div>
      <p class="module-caption">这里是当前可用数量，收藏和明细都在背包里。</p>
    </section>

    <section class="home-module" aria-labelledby="challenges-heading">
      <div class="module-heading"><h2 id="challenges-heading">⭐ 今天的冒险</h2><button class="text-button" @click="emit('navigate', 'adventures', 'all')">全部任务 →</button></div>
      <div class="challenge-overview"><button v-for="challenge in challenges" :key="challenge.id" :class="{completed: challenge.completed, inactive: !challenge.enabled}" :style="{'--accent': challenge.color}" @click="emit('navigate', 'adventures', challenge.id)">
        <span class="challenge-icon" aria-hidden="true">{{ challenge.icon }}</span><strong>{{ challenge.name }}</strong><small>{{ challenge.reward }}</small><span class="challenge-status">{{ !challenge.enabled ? '待设置' : challenge.completed ? '已完成 ✓' : '去挑战' }}</span>
      </button></div>
    </section>

    <section class="home-module next-goal" aria-labelledby="goal-heading">
      <div class="module-heading"><h2 id="goal-heading">🎁 我的下一个目标</h2><PixelArt kind="ticket" :size="28" /></div>
      <h3>{{ available >= 5 ? '集齐 5 枚徽章，可以换券啦！' : `还差 ${5 - available} 枚可用徽章` }}</h3>
      <div class="goal-meter"><progress :value="Math.min(available, 5)" max="5" aria-label="下一张兑换券所需的可用徽章" /><strong>{{ Math.min(available, 5) }} / 5 枚徽章</strong></div>
      <p>{{ available >= 5 ? '选择任意 5 枚可用徽章申请兑换券，家长审批后再用券兑换礼物。' : '继续完成冒险任务，攒满 5 枚可用徽章后就能申请兑换券。' }}</p>
      <div class="goal-actions"><button v-if="available >= 5" class="secondary-button" @click="emit('navigate', 'backpack', 'coupons')">申请兑换券 →</button><button v-else class="secondary-button" @click="emit('navigate', 'backpack', 'badges')">看看我的徽章 →</button></div>
    </section>
  </section>
</template>
