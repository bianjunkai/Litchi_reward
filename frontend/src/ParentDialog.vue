<script setup>
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
const props = defineProps({ open:Boolean, busy:Boolean, title:String })
const emit = defineEmits(['close'])
const dialog = ref(null)
const titleId = useId()
watch(() => props.open, async open => {
  await nextTick()
  if (open && !dialog.value?.open) dialog.value?.showModal()
  else if (!open) dialog.value?.close()
}, {immediate:true})
onBeforeUnmount(() => dialog.value?.close())
</script>
<template>
  <dialog ref="dialog" class="shop-confirm-dialog parent-dialog" :aria-labelledby="titleId" @cancel.prevent="!busy && emit('close')">
    <h2 :id="titleId">{{ title }}</h2><slot />
    <button class="secondary-button" autofocus :disabled="busy" @click="emit('close')">返回，不执行</button>
  </dialog>
</template>
