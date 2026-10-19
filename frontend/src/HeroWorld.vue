<script setup>
import PixelArt from './PixelArt.vue'
</script>

<template>
  <svg class="pixel-world" viewBox="0 0 640 220" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" aria-hidden="true" focusable="false">
    <defs>
      <pattern id="world-bricks" width="32" height="26" patternUnits="userSpaceOnUse"><rect width="32" height="26" fill="#cc703a" /><path d="M0 0H32V26H0Z M0 13H32 M16 0V13 M7 13V26" fill="none" stroke="#88442b" stroke-width="2" /><path d="M2 2H30M2 15H14" stroke="#f0a468" stroke-width="2" /></pattern>
      <linearGradient id="world-pipe"><stop stop-color="#258f3b" /><stop offset=".25" stop-color="#76d94b" /><stop offset=".48" stop-color="#4ac83f" /><stop offset="1" stop-color="#138634" /></linearGradient>
    </defs>
    <g fill="#fff" opacity=".92"><path d="M35 40h12V28h32v8h20v12h14v18H25V50h10z" /><path d="M330 22h16V10h32v8h18v12h14v18h-94V32h14z" /><path d="M530 45h12V33h28v8h20v12h10v14h-80V53h10z" /></g>
    <g fill="#6bc86c"><path d="M0 188v-25h18v-20h19v-21h29v-17h23v17h22v21h20v20h20v25z" /><path d="M365 188v-20h17v-25h20v-20h26v-17h30v17h24v20h20v25h19v20z" /></g>
    <g fill="#9be07a"><path d="M40 180v-28h20v-20h25v20h21v28z" /><path d="M402 188v-35h17v-25h26v25h17v35z" /></g>
    <g class="world-coins"><PixelArt kind="coin" :size="27" x="152" y="60" /><PixelArt kind="coin" :size="27" x="191" y="45" /><PixelArt kind="coin" :size="27" x="230" y="60" /></g>
    <rect x="132" y="105" width="40" height="32" fill="url(#world-bricks)" /><PixelArt kind="question" :size="36" x="172" y="101" /><rect x="208" y="105" width="40" height="32" fill="url(#world-bricks)" /><PixelArt kind="question" :size="36" x="248" y="101" />
    <PixelArt class="world-mario" kind="mario" :size="53" x="166" y="137" />
    <PixelArt kind="mushroom" :size="29" x="275" y="161" />
    <g stroke="#1b7533" stroke-width="3"><rect x="320" y="140" width="47" height="50" fill="url(#world-pipe)" /><rect x="313" y="123" width="61" height="22" fill="url(#world-pipe)" /></g>
    <g><rect x="465" y="65" width="5" height="125" fill="#f6f8e2" /><rect x="463" y="63" width="9" height="5" fill="#f6cf41" /><path d="M470 70h45v24h-45z" fill="#e94a3a" /><path d="m485 77 3 4 5 1-4 3v5l-4-3-4 3v-5l-3-3 5-1z" fill="#fff3b9" /><rect x="454" y="183" width="27" height="8" fill="#df9c56" /></g>
    <PixelArt kind="castle" :size="107" x="520" y="83" />
    <path d="M0 186h640v8H0z" fill="#79d443" /><path d="M0 194h640v26H0z" fill="url(#world-bricks)" />
  </svg>
</template>
