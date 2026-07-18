<template>
  <v-card class="fill-height">
    <v-card-title class="d-flex align-center justify-space-between">
      <span class="text-subtitle-1 font-weight-bold">Compliance Trend</span>
      <div class="d-flex ga-2 flex-wrap">
        <v-chip size="x-small" color="primary" variant="tonal" label>
          <span class="legend-dot" style="background:#1867C0" /> Avg Score
        </v-chip>
        <v-chip size="x-small" color="error" variant="tonal" label>
          <span class="legend-dot" style="background:#F44336" /> Open Violations
        </v-chip>
      </div>
    </v-card-title>
    <v-card-text>
      <div v-if="points.length < 2" class="text-center py-8 text-medium-emphasis">
        <v-icon size="40" class="mb-2">mdi-chart-line</v-icon>
        <div class="text-body-2">Trend appears after a few scans.</div>
        <div class="text-caption">Each completed scan adds a data point.</div>
      </div>
      <svg v-else :viewBox="`0 0 ${W} ${H}`" width="100%" preserveAspectRatio="xMidYMid meet"
           role="img" aria-label="Compliance trend over time">
        <!-- gridlines + score axis (0–100) -->
        <g v-for="g in [0, 50, 100]" :key="g">
          <line :x1="PAD" :x2="W - PAD" :y1="sy(g)" :y2="sy(g)"
                stroke="currentColor" stroke-opacity="0.12" stroke-width="1" />
          <text :x="PAD - 6" :y="sy(g) + 3" text-anchor="end" font-size="9"
                fill="currentColor" fill-opacity="0.55">{{ g }}</text>
        </g>
        <!-- avg score area + line -->
        <polygon :points="scoreArea" fill="#1867C0" fill-opacity="0.08" />
        <polyline :points="scoreLine" fill="none" stroke="#1867C0" stroke-width="2"
                  stroke-linejoin="round" stroke-linecap="round" />
        <!-- open violations line (scaled to its own max) -->
        <polyline :points="violLine" fill="none" stroke="#F44336" stroke-width="2"
                  stroke-dasharray="4 3" stroke-linejoin="round" stroke-linecap="round" />
        <!-- points with tooltips -->
        <g v-for="(p, i) in points" :key="i">
          <circle :cx="px(i)" :cy="sy(p.score ?? 0)" r="3" fill="#1867C0">
            <title>{{ p.label }} — avg score {{ p.score ?? '—' }}</title>
          </circle>
          <circle :cx="px(i)" :cy="vy(p.violations)" r="3" fill="#F44336">
            <title>{{ p.label }} — {{ p.violations }} open violations</title>
          </circle>
        </g>
        <!-- x labels -->
        <text :x="PAD" :y="H - 4" font-size="9" fill="currentColor" fill-opacity="0.55">
          {{ points[0].label }}</text>
        <text :x="W - PAD" :y="H - 4" text-anchor="end" font-size="9"
              fill="currentColor" fill-opacity="0.55">{{ points[points.length - 1].label }}</text>
      </svg>
    </v-card-text>
  </v-card>
</template>

<script setup>
/**
 * TrendChart — dependency-free SVG chart of avg compliance score and open
 * violations over time, sourced from scan_complete audit-log entries.
 * Older entries lack avg_score (added 2026-07); those points carry the
 * violations series only.
 */
import { ref, computed, onMounted } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

const W = 560, H = 170, PAD = 28
const points = ref([])

const px = (i) => PAD + (i * (W - 2 * PAD)) / Math.max(points.value.length - 1, 1)
const sy = (score) => (H - 22) - (score / 100) * (H - 40)
const maxViol = computed(() =>
  Math.max(1, ...points.value.map(p => p.violations)))
const vy = (v) => (H - 22) - (v / maxViol.value) * (H - 40)

const scoreLine = computed(() =>
  points.value.map((p, i) => `${px(i)},${sy(p.score ?? 0)}`).join(' '))
const scoreArea = computed(() =>
  `${PAD},${sy(0)} ${scoreLine.value} ${px(points.value.length - 1)},${sy(0)}`)
const violLine = computed(() =>
  points.value.map((p, i) => `${px(i)},${vy(p.violations)}`).join(' '))

onMounted(async () => {
  try {
    const data = await GovernanceService.getAuditLog(200)
    const scans = data
      .filter(r => r.event === 'scan_complete')
      .map(r => {
        // Backend returns details already parsed (object); tolerate legacy JSON.
        let d = r.details
        if (!d) { try { d = JSON.parse(r.details_json || '{}') } catch { d = {} } }
        return {
          ts:         r.timestamp_utc,
          label:      new Date(r.timestamp_utc).toLocaleDateString(),
          score:      d.avg_score ?? null,
          violations: Number(d.open_violations ?? 0),
        }
      })
      .reverse()                                  // API returns newest first
    points.value = scans
  } catch (e) {
    console.warn('[trend] failed to load audit log:', e.message)
  }
})
</script>

<style scoped>
.legend-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 4px;
}
</style>
