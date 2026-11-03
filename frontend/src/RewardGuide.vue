<script setup>
import PixelArt from './PixelArt.vue'
</script>
<template>
  <section class="reward-guide" aria-label="家庭奖励规则">
    <h2>我们的奖励路线</h2>
    <div class="reward-sources">
      <div><PixelArt kind="sunflower" :size="28" /><strong>5 颗橙色学习星星 → 太阳花徽章</strong><span>橙色星星单独累计，换 1 枚学习徽章</span></div>
      <div><PixelArt kind="star" :size="28" :style="{'--pixel-accent':'#41a85f'}" /><strong>5 颗绿／红星星 → 生活徽章</strong><span>绿色整理星星与红色吃饭星星可以混合</span></div>
      <div><PixelArt kind="mushroom" :size="28" /><strong>完成约定运动 → 体育徽章</strong><span>家长确认后直接获得，不消耗星星</span></div>
    </div>
    <div class="reward-route">
      <div><PixelArt kind="mario" :size="28" /><strong>任意 5 枚可用徽章</strong><span>生活、体育、太阳花徽章可以混合</span></div>
      <span class="route-arrow" aria-hidden="true">→</span>
      <div><PixelArt kind="ticket" :size="28" /><strong>1 张 ¥39.90 兑换券</strong><span>可以累积 · 每次最多 5 张</span></div>
    </div>
    <p>只有已启用、未兑换的徽章参与换券；预留徽章启用后也可计入。每次最多抵用 ¥199.50，不找零、不折现。</p>
  </section>
</template>
