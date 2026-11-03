<script setup>
import PixelArt from './PixelArt.vue'
defineProps({ code: String, color: String, size: { type: Number, default: 48 } })
const badgeIcons = { sports: 'mushroom', life: 'star', fire: 'sunflower', royal: 'crown' }
</script>
<template>
  <span class="badge-emblem" :style="{'--emblem-color': color || '#f0aa37', '--pixel-accent': color || '#f0aa37'}" aria-hidden="true">
    <PixelArt :kind="badgeIcons[code] || 'star'" :size="size" />
  </span>
</template>
