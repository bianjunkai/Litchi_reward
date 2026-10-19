<script setup>
import { ref } from 'vue'
const props = defineProps({ title: String, items: Array, fields: Array, defaults: Object, disabled: Boolean, allowCreate: { type: Boolean, default: true }, description: String })
const emit = defineEmits(['save'])
const draft = ref(null)
const edit = item => { draft.value = { ...item, active: Boolean(item.active) } }
const submit = () => { emit('save', { ...draft.value }) }
const close = () => { draft.value = null }
defineExpose({ close })
</script>

<template>
  <details class="panel resource-editor">
    <summary>{{ title }}</summary>
    <p v-if="description" class="muted">{{ description }}</p>
    <div class="resource-list"><div v-for="item in items" :key="item.id" class="adjust-row"><span>{{ item.icon || '📌' }} {{ item.name }} <small>{{ item.active ? '已启用' : '已停用' }}</small></span><button :disabled="disabled" @click="edit(item)">编辑</button></div></div>
    <button v-if="allowCreate" class="secondary-button" :disabled="disabled" @click="edit(defaults)">＋ 新增</button>
    <form v-if="draft" class="editor-form" @submit.prevent="submit">
      <label v-for="field in fields.filter(field => !field.when || field.when(draft))" :key="field.key">{{ field.label }}
        <select v-if="field.options" v-model="draft[field.key]" :disabled="disabled"><option v-for="option in field.options" :key="String(option.value)" :value="option.value">{{ option.label }}</option></select>
        <input v-else-if="field.type === 'checkbox'" v-model="draft[field.key]" type="checkbox" :disabled="disabled" />
        <input v-else-if="field.type === 'number'" v-model.number="draft[field.key]" type="number" :min="field.min ?? 1" :max="field.max ?? 999" :disabled="disabled" required />
        <input v-else v-model="draft[field.key]" :type="field.type || 'text'" :inputmode="field.inputmode" :maxlength="field.maxLength || 500" :disabled="disabled || field.readOnly" :required="field.required" />
      </label>
      <div class="form-actions"><button class="primary-button" :disabled="disabled">保存{{ title.replace('管理','') }}</button><button type="button" class="secondary-button" @click="close">取消</button></div>
    </form>
  </details>
</template>
