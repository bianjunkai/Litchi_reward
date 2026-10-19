<script setup>
import { computed } from 'vue'
import PixelArt from '../PixelArt.vue'
import BadgeEmblem from '../BadgeEmblem.vue'
import { adventureTabs, routeHash } from '../navigation.js'
import { tasksForCategory } from '../page-models.js'

const props = defineProps({ tasks: Array, badges: Array, category: String, offline: Boolean })
const emit = defineEmits(['navigate'])
const visibleTasks = computed(() => tasksForCategory(props.tasks, props.badges, props.category))
const badgeFor = task => props.badges.find(badge => badge.id === task.badge_id)
</script>

<template>
  <section class="view adventures-view">
    <div class="page-title"><span class="eyebrow">QUEST BOARD</span><h1>今天的冒险 <PixelArt kind="question" :size="30" /></h1><p>认真做好每件小事，请家长确认你的努力。</p></div>
    <nav class="section-tabs" aria-label="任务类别"><a v-for="tab in adventureTabs" :key="tab.id" :href="routeHash('adventures', tab.id)" :aria-current="category === tab.id ? 'page' : undefined">{{ tab.label }}</a></nav>
    <p class="page-note">{{ category === 'sports' ? '完成约定运动，直接获得体育徽章，不消耗星星。' : '学习、整理、吃饭各奖励对应颜色星星，每项每天最多 1 枚；运动任务直接奖励体育徽章。' }}</p>
    <section v-if="!visibleTasks.length" class="panel empty-state"><h2>这一关还在准备中</h2><p>请家长启用徽章或设置任务后，再来挑战。</p><button class="secondary-button" @click="emit('navigate', 'parent', 'tasks')">请家长设置</button></section>
    <div class="task-list"><article v-for="task in visibleTasks" :key="task.id" class="task-card" :class="{completed: task.claimed_today}">
      <div class="task-symbol"><BadgeEmblem v-if="task.badge_id" :code="badgeFor(task)?.code" :color="task.badge_color || badgeFor(task)?.color" :size="32" /><PixelArt v-else kind="star" :size="32" :style="{'--pixel-accent': task.color}" /></div>
      <div class="task-info"><h2>{{ task.name }}</h2><p>{{ task.description }}</p><span class="reward-pill">{{ task.badge_name || task.asset_name }} × {{ task.amount }}</span><small v-if="task.badge_id" class="task-direct-badge">完成后直接获得徽章，不用星星兑换</small></div>
      <button :disabled="!!task.claimed_today || offline" @click="emit('navigate', 'parent', 'today')">{{ task.claimed_today ? '已完成 ✅' : '请家长确认' }}</button>
    </article></div>
  </section>
</template>
