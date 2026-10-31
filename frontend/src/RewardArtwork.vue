<script setup>
import { computed, ref, watch } from 'vue'
const props = defineProps({image:String,icon:{type:String,default:'🎁'},name:{type:String,default:'奖励'}})
const failed = ref(false)
const source = computed(() => props.image?.length <= 128050 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(props.image) ? props.image : '')
watch(() => props.image, () => { failed.value = false })
</script>
<template><div class="reward-artwork"><img v-if="source && !failed" :src="source" :alt="`${name}配图`" loading="lazy" decoding="async" @error="failed = true" /><span v-else aria-hidden="true">{{ icon || '🎁' }}</span></div></template>
