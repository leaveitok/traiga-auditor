<template>
  <v-container fluid class="pa-6">

    <!-- No city assigned warning -->
    <v-alert v-if="!auth.city" type="warning" class="mb-4">
      Your account has not been assigned to a city yet. Contact your administrator.
    </v-alert>

    <template v-if="auth.city">

      <!-- Header row -->
      <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
        <div>
          <div class="text-h5 font-weight-bold">{{ auth.city }}</div>
          <div class="text-caption text-medium-emphasis">
            Texas HB 149 / TRAIGA · Tex. Bus. &amp; Com. Code Ch. 552
          </div>
        </div>
        <AuditRunButton @audit-complete="refresh" />
      </div>

      <!-- Loading state -->
      <v-row v-if="loading">
        <v-col cols="12" class="text-center py-12">
          <v-progress-circular indeterminate color="primary" />
        </v-col>
      </v-row>

      <!-- No data yet -->
      <v-alert v-else-if="!cityRow" type="info" variant="tonal" class="mb-4">
        No compliance data yet for <strong>{{ auth.city }}</strong>. Run an audit to get started.
      </v-alert>

      <template v-else>

        <!-- Hero card -->
        <v-card class="mb-6" :color="bandColor" variant="tonal">
          <v-card-item>
            <template #prepend>
              <v-avatar :color="bandColor" size="56">
                <v-icon size="30" color="white">mdi-city</v-icon>
              </v-avatar>
            </template>
            <v-card-title class="text-h5">{{ cityRow.city }}</v-card-title>
            <v-card-subtitle>{{ cityRow.jurisdiction }} · {{ cityRow.domain }}</v-card-subtitle>
            <template #append>
              <div class="text-right">
                <div class="text-h3 font-weight-bold">{{ cityRow.compliance_score }}</div>
                <div class="text-caption text-medium-emphasis">Compliance Score</div>
              </div>
            </template>
          </v-card-item>
          <v-card-text>
            <div class="d-flex align-center justify-space-between flex-wrap ga-3">
              <div class="d-flex align-center ga-3 flex-wrap">
                <ComplianceStatusChip :status="cityRow.traiga_status" />
                <v-chip size="small" label prepend-icon="mdi-alert-circle-outline"
                        :color="Number(cityRow.open_violations_count) > 0 ? 'error' : 'success'">
                  {{ cityRow.open_violations_count }} open violation{{ cityRow.open_violations_count == 1 ? '' : 's' }}
                </v-chip>
                <v-chip size="small" label prepend-icon="mdi-clock-outline" color="default">
                  Last scanned {{ fmtDate(cityRow.last_scanned_utc) }}
                </v-chip>
              </div>
              <v-btn color="primary" variant="elevated"
                     prepend-icon="mdi-file-document-outline"
                     :loading="generatingReport"
                     :disabled="cityRow.traiga_status === 'not_assessed'"
                     @click="downloadReport">
                Generate Compliance Report
              </v-btn>
            </div>
          </v-card-text>
        </v-card>

        <!-- Two-column layout -->
        <v-row>
          <v-col cols="12" lg="8">

            <!-- AI Assets -->
            <v-card class="mb-4">
              <v-card-title prepend-icon="mdi-robot">
                AI Assets Detected
                <v-chip class="ml-2" size="x-small" color="primary" label>{{ assets.length }}</v-chip>
              </v-card-title>
              <v-card-text v-if="assets.length === 0" class="text-medium-emphasis">
                No AI assets detected on this domain.
              </v-card-text>
              <v-list v-else lines="two">
                <v-list-item v-for="(asset, i) in assets" :key="i" :prepend-icon="assetIcon(asset)">
                  <v-list-item-title>{{ asset.display_name || asset.vendor_id }}</v-list-item-title>
                  <v-list-item-subtitle>
                    {{ Array.isArray(asset.asset_type) ? asset.asset_type.join(', ') : asset.asset_type }}
                    · Confidence {{ Math.round((asset.match_confidence || 0) * 100) }}%
                  </v-list-item-subtitle>
                  <template #append>
                    <v-chip size="x-small" label
                            :color="asset.verification_status === 'verified' ? 'success' : 'warning'">
                      {{ asset.verification_status || 'unverified' }}
                    </v-chip>
                  </template>
                </v-list-item>
              </v-list>
            </v-card>

            <!-- Violations -->
            <v-card>
              <v-card-title prepend-icon="mdi-alert-circle">
                Violations &amp; Cure Period
                <v-chip class="ml-2" size="x-small" color="error" label>{{ violations.length }}</v-chip>
              </v-card-title>
              <div v-if="violations.length === 0" class="pa-4 text-medium-emphasis">
                No open violations.
              </div>
              <v-expansion-panels v-else variant="accordion" flat>
                <v-expansion-panel v-for="v in violations" :key="v.violation_id">
                  <v-expansion-panel-title>
                    <div class="d-flex align-center ga-3 flex-wrap" style="width:100%">
                      <CurePeriodGauge :days="parseDays(v.days_remaining)" :size="40" />
                      <div>
                        <div class="font-weight-medium">{{ v.rule_id }}</div>
                        <a :href="citationUrl(v.citation)" target="_blank" rel="noopener"
                           class="text-caption text-primary" style="text-decoration:underline dotted"
                           @click.stop>{{ v.citation }}</a>
                      </div>
                      <v-spacer />
                      <ComplianceStatusChip :status="v.status" />
                      <v-chip size="x-small" :color="severityColor(v.severity)" label>{{ v.severity }}</v-chip>
                    </div>
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <v-list density="compact" class="mb-2">
                      <v-list-item title="Violation ID"   :subtitle="v.violation_id" />
                      <v-list-item title="Vendor"         :subtitle="v.vendor_id" />
                      <v-list-item title="First Observed" :subtitle="fmtDate(v.first_observed_utc)" />
                      <v-list-item title="Cure Deadline"  :subtitle="fmtDate(v.cure_deadline_utc)" />
                      <v-list-item title="Days Remaining" :subtitle="String(parseDays(v.days_remaining) ?? '—')" />
                      <v-list-item title="Statutory Citation">
                        <template #subtitle>
                          <div class="d-flex flex-column ga-1 mt-1">
                            <a :href="citationUrl(v.citation)" target="_blank" rel="noopener" class="text-primary text-caption">
                              {{ v.citation }} ↗
                            </a>
                            <a :href="HB149_URL" target="_blank" rel="noopener" class="text-primary text-caption">
                              Texas HB 149 (89th Legislature) ↗
                            </a>
                          </div>
                        </template>
                      </v-list-item>
                    </v-list>
                    <div v-if="v.evidence?.remediation" class="mt-2">
                      <div class="text-subtitle-2 mb-1">Remediation</div>
                      <v-alert type="info" variant="tonal" density="compact">{{ v.evidence.remediation }}</v-alert>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-card>

          </v-col>

          <!-- Right col: Cure summary + legal notice -->
          <v-col cols="12" lg="4">
            <v-card class="mb-4">
              <v-card-title>Cure Period Summary</v-card-title>
              <v-card-text>
                <div class="d-flex justify-center mb-4">
                  <CurePeriodGauge :days="minDays" :size="100" />
                </div>
                <v-list density="compact">
                  <v-list-item title="Tightest deadline"
                               :subtitle="minDays !== null ? `${minDays} days remaining` : 'No active cure periods'" />
                  <v-list-item title="Statutory basis" subtitle="Texas HB 149 § 552 · 60-day cure window" />
                </v-list>
              </v-card-text>
            </v-card>

            <v-card variant="outlined">
              <v-card-text class="text-caption text-medium-emphasis">
                Findings are candidate compliance signals from externally observable evidence.
                Human and legal review required before enforcement action.
                Cite <a href="https://statutes.capitol.texas.gov/Docs/BC/htm/BC.552.htm"
                        target="_blank">Tex. Bus. &amp; Com. Code Ch. 552</a>.
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>

      </template>
    </template>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>

  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useAuthStore }       from '../stores/auth'
import { useScorecardStore }  from '../stores/scorecard'
import { useViolationsStore } from '../stores/violations'
import { useAuditStore }      from '../stores/audit'
import AuditRunButton       from '../components/AuditRunButton.vue'
import ComplianceStatusChip from '../components/ComplianceStatusChip.vue'
import CurePeriodGauge      from '../components/CurePeriodGauge.vue'
import { useReportsStore } from '../stores/reports'

const auth       = useAuthStore()
const scStore    = useScorecardStore()
const vStore     = useViolationsStore()
const auditStore = useAuditStore()
const rStore     = useReportsStore()
const loading    = ref(true)
const snackbar   = reactive({ show: false, text: '', color: 'success' })

/** Tracks spinner state — store owns this, not a local ref. */
const generatingReport = computed(() => rStore.isGenerating(auth.city))

const STATUTE_BASE = 'https://statutes.capitol.texas.gov/Docs/BC/htm/BC.552.htm'
const HB149_URL    = 'https://capitol.texas.gov/tlodocs/89R/billtext/html/HB00149F.htm'
const citationUrl  = (c) => { if (!c) return STATUTE_BASE; const m = c.match(/§\s*(552\.\d+)/); return m ? `${STATUTE_BASE}#${m[1]}` : STATUTE_BASE }

const cityRow = computed(() => scStore.rows.find(r => r.city === auth.city) || null)

const assets = computed(() => {
  if (!cityRow.value) return []
  try { const raw = cityRow.value.ai_assets || cityRow.value.ai_assets_json; if (!raw) return []; return typeof raw === 'string' ? JSON.parse(raw) : raw }
  catch { return [] }
})

const violations = computed(() =>
  vStore.items.filter(v => v.city === auth.city && v.status !== 'cured')
)

const minDays = computed(() => {
  const days = violations.value.map(v => parseDays(v.days_remaining)).filter(d => d !== null)
  return days.length ? Math.min(...days) : null
})

const bandColor = computed(() => ({ green: 'success', amber: 'warning', red: 'error' })[cityRow.value?.band] || 'primary')

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—'
const parseDays = (val) => { if (val === null || val === undefined || val === '' || val === 'None') return null; const n = Number(val); return isNaN(n) ? null : n }
const severityColor = (s) => ({ high: 'error', medium: 'warning', low: 'info' }[s] || 'default')
const assetIcon = (asset) => { const t = Array.isArray(asset.asset_type) ? asset.asset_type : [asset.asset_type]; if (t.some(x => String(x).includes('chatbot'))) return 'mdi-chat-processing'; if (t.some(x => String(x).includes('voice'))) return 'mdi-microphone'; return 'mdi-robot' }

async function refresh() {
  await Promise.all([scStore.fetchScorecard(), vStore.fetchViolations()])
}

async function downloadReport() {
  if (!auth.city) return
  // Layering: store calls GovernanceService — component never touches it directly.
  const ok = await rStore.download(auth.city)
  snackbar.text  = ok ? 'Report downloaded' : `Report failed: ${rStore.error}`
  snackbar.color = ok ? 'success' : 'error'
  snackbar.show  = true
}

// Auto-refresh when an audit finishes
watch(() => auditStore.status, (s) => { if (s === 'completed') refresh() })

onMounted(async () => {
  await Promise.all([
    scStore.rows.length   === 0 ? scStore.fetchScorecard()   : Promise.resolve(),
    vStore.items.length   === 0 ? vStore.fetchViolations()   : Promise.resolve(),
  ])
  loading.value = false
})
</script>
