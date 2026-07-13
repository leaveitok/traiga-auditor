<template>
  <v-card class="fill-height">
    <v-card-title class="d-flex align-center justify-space-between">
      <span class="text-subtitle-1 font-weight-bold">Texas Compliance Map</span>
      <div class="d-flex align-center ga-1">
        <span class="text-caption text-medium-emphasis mr-1">{{ pins.length }} of {{ rows.length }} mapped</span>
        <v-btn icon="mdi-minus" size="x-small" variant="text" title="Zoom out" @click="zoomBy(1 / STEP)" />
        <v-btn icon="mdi-plus" size="x-small" variant="text" title="Zoom in" @click="zoomBy(STEP)" />
        <v-btn icon="mdi-restore" size="x-small" variant="text" title="Reset view"
               :disabled="isDefault" @click="resetView" />
      </div>
    </v-card-title>
    <v-card-text>
      <svg ref="svgEl" :viewBox="viewBox" width="100%" preserveAspectRatio="xMidYMid meet"
           :style="{ cursor: dragging ? 'grabbing' : 'grab', touchAction: 'none' }"
           role="img" aria-label="Map of Texas with monitored cities colored by TRAIGA status. Scroll to zoom, drag to pan, double-click to zoom in."
           @wheel.prevent="onWheel" @mousedown="onDown" @dblclick.prevent="onDblClick">
        <!-- Texas outline (simplified border, equirectangular projection) -->
        <polygon :points="outline" fill="currentColor" fill-opacity="0.06"
                 stroke="currentColor" stroke-opacity="0.35" :stroke-width="1.5 / zoom"
                 stroke-linejoin="round" />
        <!-- city pins at their TRUE positions. Radii are counter-scaled by zoom so
             they stay a constant on-screen size — clustered cities (DFW) separate as
             you zoom into that part of the map. -->
        <g v-for="p in pins" :key="p.city" style="cursor:pointer"
           @click="onPinClick(p)">
          <circle :cx="p.x" :cy="p.y" :r="8 / zoom" :fill="p.color" fill-opacity="0.22"
                  :stroke="p.failed ? p.color : 'none'" :stroke-width="1.5 / zoom"
                  :stroke-dasharray="p.failed ? `${3 / zoom},${2 / zoom}` : null">
            <title>{{ p.city }} — {{ p.statusLabel }}</title>
          </circle>
          <circle :cx="p.x" :cy="p.y" :r="4 / zoom" :fill="p.color" stroke="white" :stroke-width="1.1 / zoom">
            <title>{{ p.city }} — {{ p.statusLabel }}</title>
          </circle>
        </g>
      </svg>
      <div class="text-caption text-medium-emphasis mt-1">
        Scroll (or double-click) to zoom in on an area · drag to pan · click a city to open it
      </div>
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
 *
 * Zoom/pan: the viewBox is reactive. Cities are drawn at their TRUE positions.
 * Scroll (or double-click) zooms IN toward the pointer; drag pans; the buttons
 * zoom around the current view centre (pan a cluster to the middle, then zoom
 * into it). Pin radii are divided by the zoom factor so markers stay a constant
 * on-screen size — so a dense metro (DFW) separates cleanly as you zoom into it,
 * without ever misrepresenting where a city actually is.
 */
import { ref, reactive, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  /** Scorecard rows: [{city, traiga_status, ...}] */
  rows: { type: Array, default: () => [] },
})

const router = useRouter()

const W = 460, H = 440
const STEP = 1.5          // zoom factor per button press
const MIN_W = W / 16      // deepest zoom (16x) — enough to split the DFW metroplex
const MAX_W = W           // fully zoomed out = default

// Reactive viewBox drives zoom + pan.
const view = reactive({ x: 0, y: 0, w: W, h: H })
const viewBox   = computed(() => `${view.x.toFixed(2)} ${view.y.toFixed(2)} ${view.w.toFixed(2)} ${view.h.toFixed(2)}`)
const zoom      = computed(() => W / view.w)
const isDefault = computed(() => view.x === 0 && view.y === 0 && view.w === W && view.h === H)
const svgEl     = ref(null)
const dragging  = ref(false)

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
  // tx100 sweep-2 cohort (2026-07-12) — approximate map positions
  'pasadena': [-95.209, 29.691],    'mcallen': [-98.230, 26.203],
  'pearland': [-95.286, 29.564],    'sugar land': [-95.635, 29.620],
  'college station': [-96.314, 30.628], 'league city': [-95.095, 29.507],
  'bryan': [-96.374, 30.674],       'baytown': [-94.977, 29.743],
  'pflugerville': [-97.620, 30.439], 'missouri city': [-95.538, 29.619],
  'temple': [-97.363, 31.098],      'flower mound': [-97.097, 33.014],
  'cedar park': [-97.820, 30.505],  'georgetown': [-97.678, 30.633],
  'port arthur': [-93.940, 29.885], 'san angelo': [-100.437, 31.464],
  'new braunfels': [-98.124, 29.703], 'conroe': [-95.456, 30.312],
  'mission': [-98.325, 26.216],     'longview': [-94.740, 32.500],
  'edinburg': [-98.163, 26.302],    'pharr': [-98.184, 26.195],
  'harlingen': [-97.696, 26.190],   'victoria': [-96.985, 28.805],
  'galveston': [-94.798, 29.301],   'san marcos': [-97.941, 29.883],
  'leander': [-97.853, 30.579],     'texas city': [-94.903, 29.384],
  'kyle': [-97.877, 29.989],        'hutto': [-97.547, 30.543],
  'weslaco': [-97.990, 26.159],     'lufkin': [-94.729, 31.338],
  'nacogdoches': [-94.655, 31.604], 'del rio': [-100.897, 29.363],
  'big spring': [-101.478, 32.250], 'paris': [-95.556, 33.661],
  'marshall': [-94.368, 32.545],    'cleburne': [-97.387, 32.348],
  'rosenberg': [-95.809, 29.557],   'sachse': [-96.595, 32.976],
  'corsicana': [-96.469, 32.095],   'kerrville': [-99.140, 30.047],
  'copperas cove': [-97.903, 31.124], 'seguin': [-97.965, 29.569],
  'forney': [-96.472, 32.748],      'prosper': [-96.801, 33.236],
  'deer park': [-95.124, 29.705],   'la porte': [-95.019, 29.665],
  'denison': [-96.567, 33.756],     'texarkana': [-94.048, 33.425],
  'balch springs': [-96.623, 32.729], 'saginaw': [-97.363, 32.860],
  'belton': [-97.464, 31.056],      'southlake': [-97.134, 32.941],
  'colleyville': [-97.155, 32.881], 'katy': [-95.816, 29.786],
  'stephenville': [-98.202, 32.220], 'greenville': [-96.111, 33.139],
  'burleson': [-97.321, 32.542],    'huntsville': [-95.551, 30.723],
  'rockwall': [-96.460, 32.931],    'friendswood': [-95.201, 29.529],
  'haltom city': [-97.269, 32.799], 'waxahachie': [-96.848, 32.386],
  'schertz': [-98.269, 29.552],
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
  review_needed:  { color: '#F57C00', label: 'Review Needed', failed: true },
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

// ── Zoom / pan ──────────────────────────────────────────────────────────────
function clampView() {
  view.w = Math.min(MAX_W, Math.max(MIN_W, view.w))
  view.h = view.w * (H / W)
  // Keep the view centre within the map so you can never lose it entirely.
  view.x = Math.min(W - view.w / 2, Math.max(-view.w / 2, view.x))
  view.y = Math.min(H - view.h / 2, Math.max(-view.h / 2, view.y))
}

// Zoom keeping the SVG point (cx,cy) fixed. factor > 1 zooms in.
function zoomAt(factor, cx, cy) {
  const rx = (cx - view.x) / view.w
  const ry = (cy - view.y) / view.h
  view.w = Math.min(MAX_W, Math.max(MIN_W, view.w / factor))
  view.h = view.w * (H / W)
  view.x = cx - rx * view.w
  view.y = cy - ry * view.h
  clampView()
}
// Buttons zoom around the current view centre: pan a cluster to the middle,
// then zoom into it.
function zoomBy(factor) {
  zoomAt(factor, view.x + view.w / 2, view.y + view.h / 2)
}
function resetView() { view.x = 0; view.y = 0; view.w = W; view.h = H }

function svgPoint(evt) {
  const rect = svgEl.value.getBoundingClientRect()
  return {
    x: view.x + ((evt.clientX - rect.left) / rect.width) * view.w,
    y: view.y + ((evt.clientY - rect.top) / rect.height) * view.h,
  }
}
function onWheel(evt) {
  if (!svgEl.value) return
  const p = svgPoint(evt)
  zoomAt(evt.deltaY < 0 ? 1.15 : 1 / 1.15, p.x, p.y)
}
function onDblClick(evt) {
  if (!svgEl.value) return
  const p = svgPoint(evt)
  zoomAt(2, p.x, p.y)   // dive in on the double-clicked spot
}

let last = null, moved = false
function onDown(evt) {
  dragging.value = true; moved = false
  last = { x: evt.clientX, y: evt.clientY }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
function onMove(evt) {
  if (!dragging.value || !svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  if (Math.abs(evt.clientX - last.x) + Math.abs(evt.clientY - last.y) > 3) moved = true
  view.x -= ((evt.clientX - last.x) / rect.width) * view.w
  view.y -= ((evt.clientY - last.y) / rect.height) * view.h
  clampView()
  last = { x: evt.clientX, y: evt.clientY }
}
function onUp() {
  dragging.value = false
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
}
onBeforeUnmount(onUp)

// Suppress click-through when the pointer was actually dragging the map.
function onPinClick(p) {
  if (moved) return
  router.push(`/city/${encodeURIComponent(p.city)}`)
}
</script>

<style scoped>
.legend-dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 50%; margin-right: 4px;
}
</style>
