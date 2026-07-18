<template>
  <v-container fluid class="pa-3 pa-sm-6">
    <div class="d-flex align-center mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Analytics</div>
        <div class="text-caption text-medium-emphasis">
          Compliance trend, discovery reach, and cross-jurisdiction AI intelligence
        </div>
      </div>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" :loading="store.loading" @click="store.fetch()" />
    </div>

    <v-alert v-if="store.error" type="error" variant="tonal" density="compact" class="mb-4">
      {{ store.error }}
    </v-alert>

    <template v-if="d">
      <!-- KPI strip -->
      <v-row class="mb-2">
        <v-col v-for="kpi in kpis" :key="kpi.label" cols="6" md="2">
          <v-card variant="tonal" :color="kpi.color">
            <v-card-text class="text-center py-4">
              <div class="text-h4 font-weight-bold">{{ kpi.value }}</div>
              <div class="text-caption">{{ kpi.label }}</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Compliance trend over time -->
      <v-card class="mb-4">
        <v-card-title>Compliance trend</v-card-title>
        <v-card-text><TrendChart /></v-card-text>
      </v-card>

      <!-- Vendor prevalence — the cross-city moat metric -->
      <v-card class="mb-4">
        <v-card-title>
          <v-icon class="mr-2">mdi-earth</v-icon>AI tools across your cities
        </v-card-title>
        <v-card-text>
          <div v-if="!d.vendor_prevalence?.length" class="text-medium-emphasis">No AI discovered yet.</div>
          <div v-for="t in d.vendor_prevalence" :key="t.tool_id" class="mb-2">
            <div class="d-flex justify-space-between text-body-2">
              <span>{{ t.display_name }}</span>
              <span class="text-medium-emphasis">{{ t.city_count }} cit{{ t.city_count === 1 ? 'y' : 'ies' }}</span>
            </div>
            <v-progress-linear :model-value="pct(t.city_count, maxPrevalence)" color="indigo" height="8" rounded />
          </div>
        </v-card-text>
      </v-card>

      <v-row>
        <!-- How AI is discovered -->
        <v-col cols="12" md="6">
          <v-card class="h-100">
            <v-card-title>How AI is discovered</v-card-title>
            <v-card-text>
              <div v-for="(n, prov) in d.provenance_breakdown" :key="prov" class="mb-2">
                <div class="d-flex justify-space-between text-body-2">
                  <span>{{ provLabel(prov) }}</span><span class="text-medium-emphasis">{{ n }}</span>
                </div>
                <v-progress-linear :model-value="pct(n, maxProvenance)" :color="provColor(prov)" height="8" rounded />
              </div>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Cure-clock aging -->
        <v-col cols="12" md="6">
          <v-card class="h-100">
            <v-card-title>Cure-clock aging (open violations)</v-card-title>
            <v-card-text>
              <div v-for="(n, bucket) in d.cure_aging" :key="bucket" class="mb-2">
                <div class="d-flex justify-space-between text-body-2">
                  <span>{{ bucket }}</span><span class="text-medium-emphasis">{{ n }}</span>
                </div>
                <v-progress-linear :model-value="pct(n, maxAging)"
                                   :color="bucket === 'expired' ? 'error' : bucket.startsWith('0-15') ? 'orange' : 'amber'"
                                   height="8" rounded />
              </div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Compliance status distribution -->
      <v-card class="mt-4">
        <v-card-title>Compliance status</v-card-title>
        <v-card-text>
          <v-chip v-for="(n, s) in d.status_distribution" :key="s" class="ma-1"
                  :color="statusColor(s)" variant="tonal">
            {{ statusLabel(s) }}: {{ n }}
          </v-chip>
        </v-card-text>
      </v-card>
    </template>

    <v-skeleton-loader v-else-if="store.loading" type="card, card" />
  </v-container>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useAnalyticsStore } from '../stores/analytics'
import TrendChart from '../components/TrendChart.vue'

const store = useAnalyticsStore()
const d = computed(() => store.data)

const kpis = computed(() => {
  const t = d.value?.totals || {}
  return [
    { label: 'Cities',           value: t.cities ?? 0,          color: 'primary' },
    { label: 'AI systems',       value: t.ai_assets ?? 0,       color: 'indigo' },
    { label: 'Needs attestation', value: t.needs_attestation ?? 0, color: 'amber' },
    { label: 'Attested',         value: t.attested ?? 0,        color: 'success' },
    { label: 'Open violations',  value: t.open_violations ?? 0, color: 'error' },
    { label: 'Avg score',        value: t.avg_score ?? '—',     color: 'teal' },
  ]
})

const pct = (n, max) => max > 0 ? Math.round((n / max) * 100) : 0
const maxPrevalence = computed(() => Math.max(1, ...(d.value?.vendor_prevalence || []).map(t => t.city_count)))
const maxProvenance = computed(() => Math.max(1, ...Object.values(d.value?.provenance_breakdown || {})))
const maxAging      = computed(() => Math.max(1, ...Object.values(d.value?.cure_aging || {})))

const PROV = {
  discovered_scan:      ['Website scan', 'blue'],
  discovered_sentinel:  ['Staff usage (Sentinel)', 'deep-purple'],
  discovered_procurement: ['Procurement', 'teal'],
  discovered_agenda:    ['Council agendas', 'indigo'],
  declared:             ['Declared', 'grey'],
}
const provLabel = (p) => (PROV[p]?.[0]) || p
const provColor = (p) => (PROV[p]?.[1]) || 'grey'

const STATUS = {
  compliant: ['Compliant', 'success'], in_cure: ['In cure', 'amber'],
  non_compliant: ['Non-compliant', 'error'], expired: ['Expired', 'error'],
  no_ai_detected: ['No AI detected', 'blue-grey'], scan_failed: ['Scan failed', 'deep-purple'],
  not_assessed: ['Not assessed', 'grey'],
}
const statusLabel = (s) => (STATUS[s]?.[0]) || s
const statusColor = (s) => (STATUS[s]?.[1]) || 'grey'

onMounted(store.fetch)
</script>
