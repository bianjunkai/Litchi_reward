<script setup>
import { computed } from 'vue'

const props = defineProps({ kind: { type: String, default: 'star' }, size: { type: Number, default: 24 } })
const palette = {
  r: '#ed4238', b: '#573123', s: '#ffc83d', f: '#ffc59b', u: '#2674dc',
  y: '#ffe983', w: '#fff8e2', k: '#26333e', g: '#38ad49', d: '#19783b',
  o: '#cd6935', t: '#f3b477', a: 'var(--pixel-accent, #ffc83d)',
}
// Tiny local pixel drawings: no external images, fonts, or network requests.
const patterns = {
  mario: [
    '.....rrrrrr.....','....rrrrrrrrrr..','....bbbffkf.....','...bfbfffkfff...',
    '...bfbbfffkfff..','...bbffffkkkk...','.....fffffff....','....rrurrru.....',
    '...rrrurrrurrr..','..rrrruuuuurrrr.','..ffruyuuuyurff.','..fffuuuuuuufff.',
    '....uuuuuuuu....','....uuu..uuu....','...bbb....bbb...','..bbbb....bbbb..',
  ],
  mushroom: [
    '.....rrrrrr.....','...rrrrrrrrrr...','..rrrwwwrrrrrr..','.rrrrwwwwrrwwrr.',
    '.rrrrrwwrrrwwwr.','rrrrrrrrrrrrrrrr','rrwwwrrrrrrwwwrr','rwwwwwrrrrwwwwwr',
    'rwwwwwrrrrwwwwwr','rrrrrrrrrrrrrrrr','.rrrrrrrrrrrrrr.','....wwwwwwww....',
    '....wwkwwkww....','....wwkwwkww....','.....wwwwww.....','......wwww......',
  ],
  star: [
    '.......aa.......','.......aa.......','......aaaa......','......aaaa......',
    '.....aaaaaa.....','.aaaaaaaaaaaaaa.','..aaaaaaaaaaaa..','...aaaaaaaaaa...',
    '....akaaaaka....','....akaaaaka....','...aaaaaaaaaa...','...aaaaaaaaaa...',
    '..aaaaa..aaaaa..','..aaaa....aaaa..','.aaa........aaa.','................',
  ],
  coin: [
    '......ssss......','....ssssssss....','...ssyyyyyyss...','..ssyssssssyss..',
    '..syssyyysssys..','.ssysssyysssyss.','.ssysssyysssyss.','.ssysssyysssyss.',
    '.ssysssyysssyss.','.ssysssyysssyss.','.ssysssyysssyss.','..syssyyysssys..',
    '..ssyssssssyss..','...ssyyyyyyss...','....ssssssss....','......ssss......',
  ],
  question: [
    'oooooooooooooooo','osssssssssssssso','osyssssssssssyso','osssswwwwwssssso',
    'ossswwkkkwwsssso','ossswwksswwsssso','ossssssswwksssso','osssssswwkssssso',
    'ossssswwksssssso','ossssswwksssssso','osssssskksssssso','ossssswwssssssso',
    'ossssswwksssssso','osysssskkssssyso','osssssssssssssso','oooooooooooooooo',
  ],
  flower: [
    '......yyyy......','....yyrrrryy....','...yrrwwwwrry...','..yrrwwkkwwrry..',
    '..yrwwwkkwwwry..','..yrrwwwwwwrry..','...yrrrrrrrry...','....yyyyyyyy....',
    '.......gg.......','..gg...gg...gg..','..gggg.gg.gggg..','...gggggggggg...',
    '....gggggggg....','.......gg.......','.......gg.......','......gggg......',
  ],
  sunflower: [
    '......ssss......','....ssssssss....','...ssssssssss...','..ssssssssssss..',
    '.ssssssssssssss.','.sssssoooosssss.','sssssoobboosssss','sssssoobboosssss',
    '.sssssoooosssss.','..ssssssssssss..','...ssssssssss...','......gggg......',
    '......gggg......','.....gggggg.....','.......gg.......','.......gg.......',
  ],
  crown: [
    '................','.ss....ss....ss.','.ss....ss....ss.','.sss..ssss..sss.',
    '.sss..ssss..sss.','.ssssssssssssss.','..ssssssssssss..','..ssrssyyssrss..',
    '..ssrssyyssrss..','..ssssssssssss..','..ssssssssssss..','...ssssssssss...',
    '...yyyyyyyyyy...','...ssssssssss...','................','................',
  ],
  castle: [
    '..ooo.oooo.ooo..','..ooo.oooo.ooo..','..oooooooooooo..','...oooooooooo...',
    '...ooottooooo...','...ooottooooo...','...oooooooooo...','...oooooooooo...',
    '.ooo.oooooo.ooo.','.ooo.oooooo.ooo.','.oooooooooooooo.','.oooooobboooooo.',
    '.oooootbbtooooo.','.ooootbbbbtoooo.','.ooootbbbbtoooo.','.ooootbbbbtoooo.',
  ],
  ticket: [
    '................','..uuuuuuuuuuuu..','.uyyyyyyyyyyyyu.','.uyyuyyyyyyyyyu.',
    '.uyyuyyssyyyyyu.','..yyuyssssyyyy..','...yuyyssyyyy...','..yyuyyyyyyyyy..',
    '.uyyuyyssyyyyyu.','.uyyuyssssyyyyu.','.uyyuyyssyyyyyu.','.uyyuyyyyyyyyyu.',
    '..uuuuuuuuuuuu..','................','................','................',
  ],
}
const cells = computed(() => (patterns[props.kind] || patterns.star).flatMap((row, y) =>
  [...row].flatMap((color, x) => palette[color] ? [{ x, y, fill: palette[color] }] : [])))
</script>

<template>
  <svg class="pixel-art" viewBox="0 0 16 16" :width="size" :height="size" xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" aria-hidden="true" focusable="false">
    <rect v-for="cell in cells" :key="`${cell.x}-${cell.y}`" :x="cell.x" :y="cell.y" width="1" height="1" :fill="cell.fill" />
  </svg>
</template>
