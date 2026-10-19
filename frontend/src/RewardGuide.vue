<script setup>
import PixelArt from './PixelArt.vue'
</script>
<template>
  <section class="reward-guide" aria-label="家庭奖励规则">
    <h2>我们的奖励路线</h2>
    <div class="reward-sources">
      <div><PixelArt kind="star" :size="28" /><strong>5 枚混色星星 → 生活徽章</strong><span>消耗 5 枚代币，换 1 枚生活徽章</span></div>
      <div><PixelArt kind="mushroom" :size="28" /><strong>完成约定运动 → 体育徽章</strong><span>家长确认后直接获得，不消耗星星</span></div>
    </div>
    <div class="reward-route">
      <div><PixelArt kind="mario" :size="28" /><strong>任意 5 枚可用徽章</strong><span>生活、体育可以混合</span></div>
      <span class="route-arrow" aria-hidden="true">→</span>
      <div><PixelArt kind="ticket" :size="28" /><strong>1 张 ¥39.90 兑换券</strong><span>可以累积 · 每次最多 5 张</span></div>
    </div>
    <p>只有已启用、未兑换的徽章参与换券；预留徽章启用后也可计入。每次最多抵用 ¥199.50，不找零、不折现。</p>
  </section>
</template>
