<template>
  <v-container fluid class="pa-6">

    <!-- Back button -->
    <v-btn variant="text" prepend-icon="mdi-arrow-left" class="mb-4"
           @click="$router.push('/dashboard')">
      Back to Dashboard
    </v-btn>

    <!-- Loading / not found states -->
    <v-alert v-if="!cityRow && !loading" type="warning" class="mb-4">
      No scorecard data found for "{{ cityName }}". Run an audit first.
    </v-alert>

    <template v-if="cityRow">

      <!-- ── Hero header ── -->
      <v-card class="mb-6" :color="bandColor" variant="tonal">
        <v-card-item>
          <template #prepend>
            <v-avatar :color="bandColor" size="56">
              <v-icon size="30" color="white">mdi-city</v-icon>
            </v-avatar>
          </template>
          <v-card-title class="text-h5">{{ cityRow.city }}</v-card-title>
          <v-card-subtitle>
            {{ cityRow.jurisdiction }} · {{ cityRow.domain }}
          </v-card-subtitle>
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
            <div class="d-flex align-center ga-3 flex-wrap">
              <AuditRunButton :city-override="cityName" @audit-complete="refresh" />

              <!-- Deep Scan — shown when a city could not be assessed (scan failed / blocked) -->
              <v-btn v-if="['not_assessed','scan_failed'].includes(cityRow.traiga_status)"
                color="warning" variant="elevated"
                prepend-icon="mdi-magnify-scan"
                @click="deepScanDialog = true"
              >
                Deep Scan
              </v-btn>

              <template v-else>
                <v-btn
                  color="primary" variant="elevated"
                  prepend-icon="mdi-file-document-outline"
                  :loading="generatingReport"
                  @click="downloadReport"
                >
                  Compliance Report
                </v-btn>
                <v-btn
                  color="teal" variant="elevated"
                  prepend-icon="mdi-shield-check-outline"
                  :loading="generatingPolicy"
                  @click="downloadPolicy"
                >
                  AI Use Policy
                </v-btn>
              </template>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <!-- ── Two-column layout ── -->
      <v-row>

        <!-- Left col: AI Assets + Violations -->
        <v-col cols="12" lg="8">

          <!-- AI Assets Detected -->
          <v-card class="mb-4">
            <v-card-title prepend-icon="mdi-robot">
              AI Assets Detected
              <v-chip class="ml-2" size="x-small" color="primary" label>
                {{ assets.length }}
              </v-chip>
            </v-card-title>
            <v-card-text v-if="assets.length === 0" class="text-medium-emphasis">
              No AI assets detected on this domain.
            </v-card-text>
            <v-list v-else lines="two">
              <v-list-item
                v-for="(asset, i) in assets"
                :key="i"
                :prepend-icon="assetIcon(asset)"
              >
                <v-list-item-title>
                  {{ asset.display_name || asset.vendor_id }}
                </v-list-item-title>
                <v-list-item-subtitle>
                  {{ Array.isArray(asset.asset_type) ? asset.asset_type.join(', ') : asset.asset_type }}
                  · Confidence {{ Math.round((asset.match_confidence || 0) * 100) }}%
                  · {{ asset.page_url }}
                </v-list-item-subtitle>
                <template #append>
                  <v-chip size="x-small"
                          :color="asset.verification_status === 'verified' ? 'success' : 'warning'"
                          label>
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
              <v-chip class="ml-2" size="x-small" color="error" label>
                {{ violations.length }}
              </v-chip>
            </v-card-title>

            <div v-if="violations.length === 0" class="pa-4 text-medium-emphasis">
              No open violations for this city.
            </div>

            <v-expansion-panels v-else variant="accordion" flat>
              <v-expansion-panel
                v-for="v in violations"
                :key="v.violation_id"
              >
                <v-expansion-panel-title>
                  <div class="d-flex align-center ga-3 flex-wrap" style="width:100%">
                    <CurePeriodGauge :days="parseDays(v.days_remaining)" :size="40" />
                    <div>
                      <div class="font-weight-medium">{{ v.rule_id }}</div>
                      <a :href="citationUrl(v.citation)" target="_blank" rel="noopener"
                         class="text-caption text-primary"
                         style="text-decoration:underline dotted"
                         @click.stop>
                        {{ v.citation }}
                      </a>
                    </div>
                    <v-spacer />
                    <ComplianceStatusChip :status="v.status" />
                    <v-chip size="x-small" :color="severityColor(v.severity)" label>
                      {{ v.severity }}
                    </v-chip>
                  </div>
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-list density="compact" class="mb-2">
                    <v-list-item title="Violation ID"    :subtitle="v.violation_id" />
                    <v-list-item title="Vendor"          :subtitle="v.vendor_id" />
                    <v-list-item title="First Observed"  :subtitle="fmtDate(v.first_observed_utc)" />
                    <v-list-item title="Cure Deadline"   :subtitle="fmtDate(v.cure_deadline_utc)" />
                    <v-list-item title="Days Remaining"  :subtitle="String(parseDays(v.days_remaining) ?? '—')" />
                    <v-list-item title="Human Review"
                                 :subtitle="v.needs_human_review ? 'Required' : 'Not required'" />
                    <v-list-item title="Statutory Citation">
                      <template #subtitle>
                        <div class="d-flex flex-column ga-1 mt-1">
                          <a :href="citationUrl(v.citation)" target="_blank" rel="noopener"
                             class="text-primary text-caption">
                            {{ v.citation }} ↗
                          </a>
                          <a :href="HB149_URL" target="_blank" rel="noopener"
                             class="text-primary text-caption">
                            Texas HB 149 (89th Legislature) ↗
                          </a>
                        </div>
                      </template>
                    </v-list-item>
                  </v-list>
                  <div v-if="v.evidence?.remediation" class="mt-2">
                    <div class="text-subtitle-2 mb-1">Remediation</div>
                    <v-alert type="info" variant="tonal" density="compact">
                      {{ v.evidence.remediation }}
                    </v-alert>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-card>

        </v-col>

        <!-- Right col: Cure period summary + quick stats -->
        <v-col cols="12" lg="4">

          <!-- Cure period summary -->
          <v-card class="mb-4">
            <v-card-title>Cure Period Summary</v-card-title>
            <v-card-text>
              <div class="d-flex justify-center mb-4">
                <CurePeriodGauge
                  :days="minDays"
                  :size="100"
                />
              </div>
              <v-list density="compact">
                <v-list-item title="Tightest deadline"
                             :subtitle="minDays !== null ? `${minDays} days remaining` : 'No active cure periods'" />
                <v-list-item title="Cure deadline"
                             :subtitle="fmtDate(earliestDeadline)" />
                <v-list-item title="Statutory basis"
                             subtitle="Texas HB 149 § 552 · 60-day cure window" />
              </v-list>
            </v-card-text>
          </v-card>

          <!-- Violation breakdown -->
          <v-card class="mb-4">
            <v-card-title>Violation Breakdown</v-card-title>
            <v-card-text>
              <div v-for="item in violationBreakdown" :key="item.label"
                   class="d-flex align-center justify-space-between mb-3">
                <span class="text-body-2">{{ item.label }}</span>
                <v-chip :color="item.color" size="small" label>{{ item.count }}</v-chip>
              </div>
            </v-card-text>
          </v-card>

          <!-- Legal notice -->
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

    <!-- Report snackbar -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>

    <!-- Deep Scan dialog -->
    <v-dialog v-model="deepScanDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6 d-flex align-center ga-2">
          <v-icon color="warning">mdi-magnify-scan</v-icon>
          Deep Scan — {{ cityName }}
        </v-card-title>

        <v-card-text>
          <v-alert type="info" variant="tonal" density="compact" class="mb-4">
            This city's domain is protected by Cloudflare Enterprise and cannot be
            crawled automatically. Deep Scan uses <strong>Claude in Chrome</strong>
            to navigate the site as a real browser and extract compliance signals.
          </v-alert>

          <div class="text-subtitle-2 mb-2">How to run a Deep Scan:</div>
          <ol class="text-body-2 pl-4 mb-4" style="line-height: 2">
            <li>Copy the prompt below</li>
            <li>Paste it into your Claude (Cowork) session</li>
            <li>Claude will navigate the site, extract AI tool signals, and post results back to the backend</li>
            <li>Return here and refresh — the city will update from <em>Scan Failed</em></li>
          </ol>

          <v-textarea
            :model-value="deepScanPrompt"
            readonly
            variant="outlined"
            density="compact"
            rows="4"
            hide-details
            label="Prompt to paste into Claude"
          />
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deepScanDialog = false">Close</v-btn>
          <v-btn color="warning" prepend-icon="mdi-content-copy" @click="copyPrompt">
            Copy Prompt
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { useScorecardStore } from '../stores/scorecard'
import { useViolationsStore } from '../stores/violations'
import ComplianceStatusChip from '../components/ComplianceStatusChip.vue'
import CurePeriodGauge from '../components/CurePeriodGauge.vue'
import AuditRunButton from '../components/AuditRunButton.vue'
import { useReportsStore } from '../stores/reports'
import { useRemediationStore } from '../stores/remediation'

const route    = useRoute()
const scStore  = useScorecardStore()
const vStore   = useViolationsStore()
const rStore   = useReportsStore()
const remStore = useRemediationStore()
const loading  = ref(true)
const snackbar = reactive({ show: false, text: '', color: 'success' })

/** Tracks spinner state without a local ref — store owns this. */
const generatingReport = computed(() => rStore.isGenerating(cityName.value))
const generatingPolicy = computed(() => remStore.isGenerating(cityName.value))
const deepScanDialog   = ref(false)

async function refresh() {
  await Promise.all([scStore.fetchScorecard(), vStore.fetchViolations()])
}

const deepScanPrompt = computed(() => {
  const domain = cityRow.value?.domain || ''
  return `Please deep scan ${cityName.value} for TRAIGA AI compliance.\n\nDomain: ${domain}\n\nUse Claude in Chrome to:\n1. Navigate to ${domain || 'the city domain'}\n2. Extract all script sources, iframe origins, cookie names, visible AI disclosure text, and network requests\n3. POST the results to http://localhost:8000/api/audit/chrome-capture with persist=true, city="${cityName.value}", jurisdiction="TX"\n\nThen let me know the results.`
})

async function copyPrompt() {
  try {
    await navigator.clipboard.writeText(deepScanPrompt.value)
    snackbar.text = 'Prompt copied to clipboard'
    snackbar.color = 'success'
    snackbar.show = true
    deepScanDialog.value = false
  } catch {
    snackbar.text = 'Copy failed — select the text manually'
    snackbar.color = 'warning'
    snackbar.show = true
  }
}

async function downloadReport() {
  // Layering: store calls GovernanceService — component never touches it directly.
  const ok = await rStore.download(cityName.value)
  snackbar.text  = ok ? 'Report downloaded' : `Report failed: ${rStore.error}`
  snackbar.color = ok ? 'success' : 'error'
  snackbar.show  = true
}

async function downloadPolicy() {
  try {
    await remStore.generatePolicy(cityName.value)
    snackbar.text  = 'AI Use Policy downloaded'
    snackbar.color = 'success'
    snackbar.show  = true
  } catch {
    snackbar.text  = remStore.getError(cityName.value) || 'Policy generation failed'
    snackbar.color = 'error'
    snackbar.show  = true
  }
}

const cityName = computed(() => decodeURIComponent(route.params.cityName))

const cityRow = computed(() =>
  scStore.rows.find(r => r.city === cityName.value) || null
)

const assets = computed(() => {
  if (!cityRow.value) return []
  try {
    const raw = cityRow.value.ai_assets || cityRow.value.ai_assets_json
    if (!raw) return []
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch { return [] }
})

const violations = computed(() =>
  vStore.items.filter(v => v.city === cityName.value && v.status !== 'cured')
)

const minDays = computed(() => {
  const days = violations.value
    .map(v => parseDays(v.days_remaining))
    .filter(d => d !== null)
  return days.length ? Math.min(...days) : null
})

const earliestDeadline = computed(() => {
  const deadlines = violations.value
    .map(v => v.cure_deadline_utc)
    .filter(Boolean)
    .sort()
  return deadlines[0] || null
})

const bandColor = computed(() => ({
  green: 'success', amber: 'warning', red: 'error'
})[cityRow.value?.band] || 'primary')

const violationBreakdown = computed(() => [
  { label: 'High severity',   color: 'error',   count: violations.value.filter(v => v.severity === 'high').length   },
  { label: 'Medium severity', color: 'warning', count: violations.value.filter(v => v.severity === 'medium').length },
  { label: 'Low severity',    color: 'info',    count: violations.value.filter(v => v.severity === 'low').length    },
  { label: 'Needs review',    color: 'warning', count: violations.value.filter(v => v.needs_human_review).length    },
])

// ── helpers ──────────────────────────────────────────────────────────────────
const STATUTE_BASE = 'https://statutes.capitol.texas.gov/Docs/BC/htm/BC.552.htm'
const HB149_URL    = 'https://capitol.texas.gov/tlodocs/89R/billtext/html/HB00149F.htm'

const citationUrl = (citation) => {
  if (!citation) return STATUTE_BASE
  const m = citation.match(/§\s*(552\.\d+)/)
  return m ? `${STATUTE_BASE}#${m[1]}` : STATUTE_BASE
}

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—'

const parseDays = (val) => {
  if (val === null || val === undefined || val === '' || val === 'None') return null
  const n = Number(val)
  return isNaN(n) ? null : n
}

const severityColor = (s) => ({ high: 'error', medium: 'warning', low: 'info' }[s] || 'default')

const assetIcon = (asset) => {
  const types = Array.isArray(asset.asset_type) ? asset.asset_type : [asset.asset_type]
  if (types.some(t => String(t).includes('chatbot'))) return 'mdi-chat-processing'
  if (types.some(t => String(t).includes('voice')))   return 'mdi-microphone'
  return 'mdi-robot'
}

onMounted(async () => {
  // Always fetch fresh — data may have changed via Deep Scan or re-audit
  // since the store was last populated. Backend TTL cache keeps Sheets calls cheap.
  await Promise.all([scStore.fetchScorecard(), vStore.fetchViolations()])
  loading.value = false
})
</script>
