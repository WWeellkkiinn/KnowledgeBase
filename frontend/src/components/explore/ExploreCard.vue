<script setup lang="ts">
import { computed } from 'vue'
import type { ExploreCardData } from '@/types/api'

const props = defineProps<{ card: ExploreCardData }>()

const BADGE_STYLES: Record<string, { bg: string; color: string; text?: (v: string) => string }> = {
  SCI:    { bg: '#dbeafe', color: '#1d4ed8' },
  SSCI:   { bg: '#e0e7ff', color: '#4338ca' },
  IF:     { bg: '#dcfce7', color: '#15803d', text: v => `IF ${v}` },
  中科院: { bg: '#ffedd5', color: '#c2410c' },
  Top:    { bg: '#ffe4e6', color: '#be123c', text: () => 'Top' },
  CCF:    { bg: '#f3e8ff', color: '#7e22ce', text: v => `CCF ${v}` },
  CSSCI:  { bg: '#ccfbf1', color: '#0f766e', text: () => 'CSSCI' },
}

const banditScoreText = computed(() =>
  props.card.bandit_score != null ? `推荐 ${props.card.bandit_score.toFixed(2)}` : null,
)

const banditScoreClass = computed(() => {
  const s = props.card.bandit_score
  if (s == null) return ''
  if (s >= 0.65) return 'bandit-score--high'
  if (s < 0.45) return 'bandit-score--low'
  return 'bandit-score--mid'
})

const renderedBadges = computed(() =>
  props.card.rank_badges
    .map(b => {
      const style = BADGE_STYLES[b.label]
      if (!style) return null
      return {
        bg: style.bg,
        color: style.color,
        text: style.text ? style.text(b.value) : b.value,
      }
    })
    .filter((b): b is { bg: string; color: string; text: string } => b !== null),
)

</script>

<template>
  <div class="explore-card">
    <p class="title-line">
      <a v-if="card.url" :href="card.url" class="title-link"><strong>{{ card.title }}</strong></a>
      <strong v-else>{{ card.title }}</strong>
    </p>

    <p v-if="card.title_zh" class="title-zh"><strong>{{ card.title_zh }}</strong></p>

    <p class="meta-line">
      {{ card.display_date }}<template v-if="card.authors"> · {{ card.authors }}</template><template v-if="card.venue_name"> (<em class="venue">{{ card.venue_name }}</em><template v-if="renderedBadges.length"> · <template v-for="(b, i) in renderedBadges" :key="i"><span class="rank-badge" :style="{ background: b.bg, color: b.color }">{{ b.text }}</span><template v-if="i < renderedBadges.length - 1"> </template></template></template>)</template><template v-if="card.cited_by_count"> · cited {{ card.cited_by_count }}</template>
    </p>

    <p v-if="card.tags.length || banditScoreText" class="tags-line">
      <span v-if="banditScoreText" class="bandit-score" :class="banditScoreClass">{{ banditScoreText }}</span>
      <span v-for="tag in card.tags" :key="tag" class="tag">{{ tag }}</span>
    </p>

    <template v-if="card.llm_reason">
      <p class="section-label"><strong>为什么推给你</strong></p>
      <p class="section-body">{{ card.llm_reason }}</p>
    </template>

    <template v-if="card.research_question">
      <p class="section-label"><strong>一句话</strong></p>
      <p class="section-body">{{ card.research_question }}</p>
    </template>

    <template v-if="card.key_findings.length">
      <p class="section-label"><strong>有什么用</strong></p>
      <ul class="findings-list">
        <li v-for="(f, i) in card.key_findings" :key="i">{{ f }}</li>
      </ul>
    </template>

    <template v-if="card.methodology">
      <p class="section-label"><strong>怎么做</strong></p>
      <p class="section-body">{{ card.methodology }}</p>
    </template>
  </div>
</template>

<style scoped>
.explore-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
}

.title-line {
  margin: 0;
  font-size: 15px;
  color: #1e293b;
}

.title-link {
  color: #1e293b;
  text-decoration: none;
}

.score-badge {
  background: #f0fdf4;
  color: #16a34a;
  border-radius: 9999px;
  padding: 1px 8px;
  font-size: 11px;
  margin-left: 6px;
  font-weight: normal;
}

.title-zh {
  margin: 4px 0 0;
  font-size: 15px;
  color: #1e293b;
}

.meta-line {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
}

.venue {
  font-style: italic;
  color: #475569;
}

.rank-badge {
  border-radius: 3px;
  padding: 0 5px;
  font-size: 11px;
  font-style: normal;
}

.tags-line {
  margin: 8px 0 0;
}

.tag {
  background: #dbeafe;
  color: #1d4ed8;
  border-radius: 9999px;
  padding: 1px 9px;
  font-size: 12px;
  display: inline-block;
  margin: 2px 4px 0 0;
}

.bandit-score {
  border-radius: 9999px;
  padding: 1px 9px;
  font-size: 12px;
  display: inline-block;
  margin: 2px 4px 0 0;
  font-weight: 600;
}
.bandit-score--high { background: #ccfbf1; color: #0f766e; }
.bandit-score--mid  { background: #fef3c7; color: #92400e; }
.bandit-score--low  { background: #f1f5f9; color: #64748b; }

.section-label {
  margin: 12px 0 2px;
  color: #0f172a;
}

.section-body {
  margin: 0;
}

.findings-list {
  margin: 0;
  padding-left: 20px;
  list-style-type: disc;
}

.findings-list li {
  list-style-type: disc;
}
</style>
