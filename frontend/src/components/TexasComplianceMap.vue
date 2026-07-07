<template>
  <v-card class="fill-height">
    <v-card-title class="d-flex align-center justify-space-between">
      <span class="text-subtitle-1 font-weight-bold">Texas Compliance Map</span>
      <span class="text-caption text-medium-emphasis">{{ pins.length }} of {{ rows.length }} cities mapped</span>
    </v-card-title>
    <v-card-text>
      <svg :viewBox="`0 0 ${W} ${H}`" width="100%" preserveAspectRatio="xMidYMid meet"
           role="img" aria-label="Map of Texas with monitored cities colored by TRAIGA status">
        <!-- Texas outline (simplified border, equirectangular projection) -->
        <polygon :points="outline" fill="currentColor" fill-opacity="0.06"
                 stroke="currentColor" stroke-opacity="0.35" stroke-width="1.5"
                 stroke-linejoin="round" />
        <!-- city pins -->
        <g v-for="p in pins" :key="p.city" style="cursor:pointer"
           @click="$router.push(`/city/${encodeURIComponent(p.city)}`)">
          <circle :cx="p.x" :cy="p.y" r="9" :fill="p.color" fill-opacity="0.25"
                  :stroke="p.failed ? p.color : 'none'" stroke-width="1.5"
                  :stroke-dasharray="p.failed ? '3,2' : null">
            <title>{{ p.city }} — {{ p.statusLabel }}</title>
          </circle>
          <circle :cx="p.x" :cy="p.y" r="4.5" :fill="p.color" stroke="white" stroke-width="1.2">
            <title>{{ p.city }} — {{ p.statusLabel }}</title>
          </circle>
        </g>
      </svg>
      <!-- legend -->
      <div class="d-flex flex-wrap ga-2 mt-2">
        <v-chip v-for="l in legend" :key="l.label" size="x-small" variant="tonal" label>
          <span class="legend-dot" :style="{ background: l.color }" /> {{ l.label }}
        </v-chip>
      </div>
      <div v-if="unmapped.length" class="text-caption text-medium-emphasis mt-2">
        No map coordinates: {{ unmapped.join(', ') }}
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup>
/**
 * TexasComplianceMap — dependency-free SVG map. Cities are placed by a
 * built-in lat/lon gazetteer of Texas municipalities (extend TX_CITIES as
 * the registry grows toward the TAGITM 1,200); pins are colored by
 * traiga_status and click through to the city detail page.
 */
import { computed } from 'vue'

const props = defineProps({
  /** Scorecard rows: [{city, traiga_status, ...}] */
  rows: { type: Array, default: () => [] },
})

const W = 460, H = 440
// Texas bounding box
const LON = [-106.7, -93.4], LAT = [25.7, 36.6]
const X = (lon) => ((lon - LON[0]) / (LON[1] - LON[0])) * (W - 20) + 10
const Y = (lat) => ((LAT[1] - lat) / (LAT[1] - LAT[0])) * (H - 20) + 10

// Simplified Texas border (lon, lat) — recognizable, not surveyor-grade.
const TX_BORDER = [
  [-106.64, 31.97], [-106.62, 32.00], [-103.06, 32.00], [-103.04, 36.50],
  [-100.00, 36.50], [-100.00, 34.56], [-99.60, 34.42], [-99.20, 34.21],
  [-98.60, 34.15], [-98.10, 34.13], [-97.15, 33.90], [-96.60, 33.85],
  [-95.80, 33.86], [-95.25, 33.94], [-94.75, 33.75], [-94.04, 33.55],
  [-94.04, 31.99], [-93.85, 31.60], [-93.70, 31.20], [-93.70, 30.60],
  [-93.72, 30.05], [-93.84, 29.68], [-94.70, 29.45], [-95.30, 29.10],
  [-96.20, 28.65], [-96.80, 28.30], [-97.15, 27.85], [-97.35, 27.20],
  [-97.35, 26.40], [-97.15, 25.95], [-97.50, 25.88], [-98.10, 26.05],
  [-98.80, 26.35], [-99.20, 26.75], [-99.45, 27.20], [-99.50, 27.60],
  [-100.00, 28.05], [-100.35, 28.45], [-100.65, 29.10], [-101.40, 29.77],
  [-102.30, 29.87], [-102.85, 29.35], [-103.30, 29.00], [-103.75, 29.20],
  [-104.50, 29.60], [-104.90, 30.35], [-105.50, 30.80], [-106.20, 31.40],
]
const outline = TX_BORDER.map(([lon, lat]) => `${X(lon).toFixed(1)},${Y(lat).toFixed(1)}`).join(' ')

// Gazetteer — extend as the registry grows.
const TX_CITIES = {
  'lewisville': [-96.994, 33.046],  'dallas': [-96.797, 32.777],
  'fort worth': [-97.330, 32.755],  'arlington': [-97.108, 32.735],
  'plano': [-96.698, 33.019],       'denton': [-97.133, 33.215],
  'frisco': [-96.823, 33.150],      'mckinney': [-96.615, 33.198],
  'irving': [-96.949, 32.814],      'garland': [-96.638, 32.912],
  'carrollton': [-96.890, 32.975],  'flower mound': [-97.097, 33.014],
  'grapevine': [-97.078, 32.934],   'the colony': [-96.886, 33.089],
  'richardson': [-96.730, 32.948],  'austin': [-97.743, 30.267],
  'round rock': [-97.678, 30.508],  'houston': [-95.369, 29.760],
  'san antonio': [-98.494, 29.424], 'el paso': [-106.485, 31.759],
  'corpus christi': [-97.396, 27.800], 'lubbock': [-101.855, 33.577],
  'amarillo': [-101.831, 35.222],   'waco': [-97.146, 31.549],
  'laredo': [-99.507, 27.506],      'brownsville': [-97.497, 25.901],
  'midland': [-102.077, 31.997],    'odessa': [-102.367, 31.845],
  'abilene': [-99.733, 32.448],     'tyler': [-95.301, 32.351],
  'wichita falls': [-98.493, 33.913], 'beaumont': [-94.101, 30.080],
  'killeen': [-97.727, 31.117],
  // DFW sweep-1 cohort additions (2026-07-07)
  'grand prairie': [-96.998, 32.746], 'allen': [-96.671, 33.103],
  'mesquite': [-96.599, 32.767],    'euless': [-97.082, 32.837],
  'bedford': [-97.143, 32.844],     'hurst': [-97.170, 32.823],
  'cedar hill': [-96.956, 32.588],  'desoto': [-96.857, 32.590],
  'duncanville': [-96.908, 32.652], 'lancaster': [-96.756, 32.592],
  'rowlett': [-96.564, 32.903],     'wylie': [-96.539, 33.015],
  'keller': [-97.252, 32.935],      'coppell': [-96.990, 32.954],
  'north richland hills': [-97.229, 32.834], 'mansfield': [-97.142, 32.563],
  'farmers branch': [-96.896, 32.926], 'little elm': [-96.938, 33.163],
}

// scan_failed must NEVER look like not_assessed: a failed scan is an
// unanswered question (WAF block / crawl error), not an untouched city.
// Purple + dashed ring makes it visually impossible to read as "fine"
// (observed 2026-07-07: Fort Worth scan_failed was mistaken for clean).
const STATUS = {
  compliant:      { color: '#2E7D32', label: 'Compliant' },
  in_cure:        { color: '#FB8C00', label: 'In Cure' },
  non_compliant:  { color: '#E53935', label: 'Non-Compliant' },
  expired:        { color: '#B71C1C', label: 'Expired' },
  no_ai_detected: { color: '#00897B', label: 'No AI Detected' },
  scan_failed:    { color: '#7B1FA2', label: 'Scan Failed', failed: true },
  not_assessed:   { color: '#BDBDBD', label: 'Not Assessed' },
}

const norm = (city) => String(city || '').toLowerCase()
  .replace(/^(city|town|village) of /, '').trim()

const pins = computed(() => props.rows.flatMap((r) => {
  const coords = TX_CITIES[norm(r.city)]
  if (!coords) return []
  const s = STATUS[r.traiga_status] || STATUS.not_assessed
  return [{
    city: r.city, x: X(coords[0]), y: Y(coords[1]),
    color: s.color, statusLabel: s.label, failed: !!s.failed,
  }]
}))

const unmapped = computed(() =>
  props.rows.filter(r => !TX_CITIES[norm(r.city)]).map(r => r.city))

// Only show legend entries present on the map
const legend = computed(() => {
  const present = new Set(props.rows.map(r => r.traiga_status))
  return Object.entries(STATUS)
    .filter(([k]) => present.has(k))
    .map(([, v]) => v)
})
</script>

<style scoped>
.legend-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 4px;
}
</style>
