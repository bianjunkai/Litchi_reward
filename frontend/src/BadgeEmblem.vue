<script setup>
import PixelArt from './PixelArt.vue'
defineProps({ code: String, color: String, size: { type: Number, default: 48 } })
</script>
<template>
  <span class="badge-emblem" :style="{'--emblem-color': color || '#f0aa37'}" aria-hidden="true">
    <PixelArt v-if="code === 'sports'" kind="mushroom" :size="size" />
    <template v-else><PixelArt kind="mario" :size="size" /><PixelArt class="emblem-mark" :kind="{life:'star',fire:'flower',royal:'crown'}[code] || 'star'" :size="Math.round(size * .55)" /></template>
  </span>
</template>
