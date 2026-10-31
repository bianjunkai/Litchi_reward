<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import ParentDialog from './ParentDialog.vue'
import RewardArtwork from './RewardArtwork.vue'
import { blankReward, compressRewardImage, editReward, filterRewards, rewardPayload, rewardTemplates } from './reward-catalog.js'
import { formatMoney } from './reward-rules.js'
const props = defineProps({products:Array,disabled:Boolean,busy:Boolean,perform:Function,actionError:String})
const emit = defineEmits(['clear-error','preview-shop'])
const draft = ref(null), form = ref(null), localError = ref(''), imageBusy = ref(false), confirmation = ref(null)
const search = ref(''), status = ref('all')
const visible = computed(() => filterRewards(props.products,search.value,status.value))
const activeCount = computed(() => props.products.filter(item => item.active).length)
const disabled = computed(() => props.disabled || imageBusy.value)
let alive = true, imageVersion = 0
onBeforeUnmount(() => { alive = false; imageVersion++ })
const edit = async (item = null, template = null) => {
  if (disabled.value) return
  imageVersion++; localError.value = ''; emit('clear-error')
  draft.value = item ? editReward(item) : {...blankReward(),...template}
  await nextTick(); form.value?.scrollIntoView({behavior:'auto',block:'start'})
  form.value?.querySelector('input')?.focus({preventScroll:true})
}
const cancel = () => { if (!disabled.value) { imageVersion++; draft.value = null; localError.value = '' } }
const selectImage = async event => {
  const file = event.target.files?.[0]; event.target.value = ''
  if (!file || disabled.value || !draft.value) return
  const version = ++imageVersion, current = draft.value
  imageBusy.value = true; localError.value = ''
  try {
    const image = await compressRewardImage(file)
    if (alive && version === imageVersion && current === draft.value) draft.value.image_data = image
  } catch (err) { if (alive && version === imageVersion) localError.value = err.message }
  finally { if (alive && version === imageVersion) imageBusy.value = false }
}
const submit = active => {
  if (disabled.value || !draft.value) return
  localError.value = ''; emit('clear-error')
  try { confirmation.value = {type:'save',id:draft.value.id,payload:rewardPayload(draft.value,active)} }
  catch (err) { localError.value = err.message }
}
const toggle = item => {
  if (disabled.value) return
  emit('clear-error'); confirmation.value = {type:'availability',id:item.id,payload:{active:!item.active},name:item.name}
}
const confirm = async () => {
  if (disabled.value || !confirmation.value) return
  const item = confirmation.value
  const success = item.type === 'availability'
    ? await props.perform(`/api/parent/products/${item.id}/availability`,item.payload,'PATCH',item.payload.active ? '奖励已上架，孩子可以申请了' : '奖励已下架，历史申请仍保留')
    : await props.perform(`/api/parent/products${item.id ? `/${item.id}` : ''}`,item.payload,item.id ? 'PUT' : 'POST',item.payload.active ? '奖励已上架，孩子可以申请了' : '奖励已保存为未上架')
  if (success) { confirmation.value = null; if (item.type === 'save') draft.value = null }
}
</script>
<template>
  <div class="reward-manager-wrap">
  <section class="panel reward-manager" aria-label="奖励上架管理">
    <div class="module-heading"><h2>奖励上架 🎁</h2><button class="primary-button" :disabled="disabled" @click="edit()">＋ 新增奖励</button></div>
    <p class="muted">把门票、充值券和亲子活动放进商城。这些是可兑换奖励，不是直接发给孩子的通用兑换券。</p>
    <div class="reward-manager-stats"><span>已上架 <b>{{ activeCount }}</b></span><span>未上架 <b>{{ products.length - activeCount }}</b></span><button class="text-button" @click="emit('preview-shop')">查看孩子商城 →（将锁定家长中心）</button></div>
    <div v-if="!draft" class="reward-templates"><span>从常用奖励开始：</span><button v-for="item in rewardTemplates" :key="item.name" class="secondary-button" :disabled="disabled" @click="edit(null,item)">{{ item.label }}</button></div>
    <section v-if="draft" ref="form" class="reward-editor" aria-label="奖励编辑">
      <h3>{{ draft.id ? '编辑兑换奖励' : '创建兑换奖励' }}</h3><p class="muted">编辑或下架不会改写历史申请；上架不会增加或扣除孩子资产。</p>
      <div class="reward-editor-grid"><form id="reward-editor-form" class="editor-form" @submit.prevent="submit(true)">
        <label>奖励名称<input v-model="draft.name" maxlength="80" placeholder="例如：木马王国门票券" :disabled="disabled" required /></label>
        <label>兑换说明<textarea v-model="draft.description" rows="3" maxlength="500" placeholder="可兑换什么、如何使用、需要与家长约定的事项" :disabled="disabled"></textarea></label>
        <div class="settlement-inputs"><label>需要通用兑换券<select v-model="draft.price" :disabled="disabled"><option v-for="count in 5" :key="count" :value="count">{{ count }} 张 · ¥{{ formatMoney(count * 3990) }}</option></select></label><label>参考消费金额（元，可留空）<input v-model="draft.cash_price" inputmode="decimal" placeholder="例如 39.90" :disabled="disabled" /></label></div>
        <label>备用图标<input v-model="draft.icon" maxlength="20" placeholder="🎁" :disabled="disabled" /></label>
        <label>奖励图片（可选）<input type="file" accept="image/jpeg,image/png,image/webp" :disabled="disabled" @change="selectImage" /></label>
        <p class="muted">支持 JPG、PNG、WebP，原图小于 5MB。图片在浏览器中压缩并移除元数据，随家庭备份保存，不依赖外部图床；无图时显示图标。</p>
        <p v-if="imageBusy" role="status">正在压缩图片…</p><button v-if="draft.image_data" type="button" class="text-button" :disabled="disabled" @click="draft.image_data = ''; imageVersion++">移除图片，使用图标</button>
        <p v-if="localError" class="inline-error" role="alert">{{ localError }}</p>
        <div class="form-actions"><button class="primary-button" :disabled="disabled">{{ draft.id ? '保存并上架' : '确认上架' }}</button><button type="button" class="secondary-button" :disabled="disabled" @click="submit(false)">保存为未上架</button><button type="button" class="text-button" :disabled="disabled" @click="cancel">取消编辑</button></div>
      </form>
      <aside class="reward-preview"><span class="eyebrow">孩子将看到的奖励</span><RewardArtwork :image="draft.image_data" :icon="draft.icon" :name="draft.name" /><h3>{{ draft.name.trim() || '奖励名称' }}</h3><p class="reward-description">{{ draft.description || '在这里填写兑换说明' }}</p><strong>{{ draft.price }} 张通用兑换券 · ¥{{ formatMoney(draft.price * 3990) }}</strong><p class="muted">仅为预览，保存并上架后才会在商城出现。孩子申请后仍须家长确认。</p></aside></div>
    </section>
    <form class="parent-filters" @submit.prevent><label>查找奖励<input v-model="search" type="search" maxlength="80" placeholder="奖励名称或说明" /></label><label>上架状态<select v-model="status" aria-label="上架状态"><option value="all">全部奖励</option><option value="active">已上架</option><option value="inactive">未上架</option></select></label></form>
    <p v-if="!visible.length" class="empty">没有符合条件的奖励，可以新增或调整筛选条件。</p>
    <div class="reward-management-grid"><article v-for="item in visible" :key="item.id" class="reward-management-card" :data-reward-id="item.id"><RewardArtwork :image="item.image_data" :icon="item.icon" :name="item.name" /><div class="module-heading"><h3>{{ item.name }}</h3><span class="reward-availability" :class="{active:item.active}">{{ item.active ? '已上架' : '未上架' }}</span></div><p class="reward-description">{{ item.description || '暂未填写兑换说明' }}</p><strong>{{ item.price }} 张通用兑换券</strong><small v-if="item.cash_price_fen != null">参考消费 ¥{{ formatMoney(item.cash_price_fen) }}</small><p v-if="item.price < 1 || item.price > 5" class="inline-error">旧奖励需先修改为 1–5 张券才能重新上架。</p><div class="form-actions"><button class="secondary-button" :disabled="disabled" @click="edit(item)">编辑奖励</button><button class="text-button" :disabled="disabled || (!item.active && (item.price < 1 || item.price > 5))" @click="toggle(item)">{{ item.active ? '下架' : '上架' }}</button></div></article></div>
    <p class="muted">每张通用券价值 ¥39.90，每次最多 5 张。5 枚徽章换 1 张券的规则不变；参考金额不等于最终消费金额。</p>
  </section>
  <ParentDialog :open="!!confirmation" :busy="busy" :title="confirmation?.payload.active ? '确认上架兑换奖励' : '确认保存为未上架'" @close="confirmation = null">
    <template v-if="confirmation"><h3>{{ confirmation.payload.name || confirmation.name }}</h3><template v-if="confirmation.type === 'save'"><RewardArtwork :image="confirmation.payload.image_data" :icon="confirmation.payload.icon" :name="confirmation.payload.name" /><p class="reward-description">{{ confirmation.payload.description }}</p><p>需要 {{ confirmation.payload.price }} 张通用券，券总额 ¥{{ formatMoney(confirmation.payload.price * 3990) }}</p><p v-if="confirmation.payload.cash_price_fen != null">参考消费 ¥{{ formatMoney(confirmation.payload.cash_price_fen) }}</p></template><p>{{ confirmation.payload.active ? '确认后会显示在孩子商城，允许发起申请；不会直接发券或扣券。' : '确认后不在孩子商城展示，历史申请和已确认消费仍然保留。' }}</p><p v-if="actionError" class="inline-error" role="alert">{{ actionError }}</p><button class="primary-button" :disabled="disabled" @click="confirm">{{ confirmation.payload.active ? '确认上架奖励' : confirmation.type === 'availability' ? '确认下架奖励' : '确认保存，暂不上架' }}</button></template>
  </ParentDialog>
  </div>
</template>
