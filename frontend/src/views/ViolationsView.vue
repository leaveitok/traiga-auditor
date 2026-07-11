<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Violations &amp; Cure Periods</div>
        <div class="text-caption text-medium-emphasis">
          60-day cure clock · sorted by urgency
        </div>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-chip :color="statusFilter === 'in_cure' ? 'warning' : 'default'"
                variant="tonal" label @click="toggleFilter('in_cure')">
          In Cure ({{ vStore.openCount }})
        </v-chip>
        <v-chip :color="statusFilter === 'expired' ? 'error' : 'default'"
                variant="tonal" label @click="toggleFilter('expired')">
          Expired ({{ vStore.expiredCount }})
        </v-chip>
        <v-chip :color="statusFilter === 'cured' ? 'success' : 'default'"
                variant="tonal" label @click="toggleFilter('cured')">
          Cured ({{ vStore.curedCount }})
        </v-chip>
        <v-btn icon="mdi-refresh" variant="text" @click="refresh" />
      </div>
    </div>

    <v-alert v-if="vStore.error" type="error" class="mb-4">{{ vStore.error }}</v-alert>

    <v-row>
      <v-col v-for="v in filtered" :key="v.violation_id" cols="12" md="6" lg="4">
        <v-card hover @click="selected = v; detail = true">
          <v-card-item>
            <template #prepend>
              <CurePeriodGauge :days="liveDaysLeft(v.cure_deadline_utc) ?? v.days_remaining" :size="52" />
            </template>
            <v-card-title class="text-body-1 font-weight-bold">{{ v.city }}</v-card-title>
            <v-card-subtitle>{{ v.rule_id }} · {{ v.severity }}</v-card-subtitle>
          </v-card-item>
          <v-card-text class="pt-0">
            <div class="d-flex align-center ga-2 mb-2">
              <ComplianceStatusChip :status="v.status" />
              <v-chip size="x-small" :color="severityColor(v.severity)" label>
                {{ v.severity }}
              </v-chip>
              <v-chip v-if="v.needs_human_review" size="x-small" color="warning" label>
                Needs Review
              </v-chip>
            </div>
            <div class="text-body-2 font-weight-medium mb-1">
              <v-icon size="small" color="primary" class="mr-1">mdi-robot-outline</v-icon>
              {{ v.finding_summary || ('This site uses ' + (v.vendor_display_name || v.vendor_id)) }}
            </div>
            <div v-if="v.matched_signals && v.matched_signals.length"
                 class="text-caption text-medium-emphasis mb-2">
              Matched via: {{ v.matched_signals.join(', ') }}
            </div>
            <div class="text-caption text-medium-emphasis">{{ v.citation }}</div>
            <div class="text-caption mt-1">
              First observed: {{ fmtDate(v.first_observed_utc) }} ·
              Deadline: {{ fmtDate(v.cure_deadline_utc) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <div v-if="!vStore.loading && filtered.length === 0"
         class="text-center text-medium-emphasis pa-12">
      <v-icon size="64" class="mb-3">mdi-check-circle-outline</v-icon>
      <div>No violations match the current filter.</div>
    </div>

    <!-- Detail drawer -->
    <v-navigation-drawer v-model="detail" location="right" width="420" temporary>
      <v-card flat v-if="selected" class="pa-4">
        <v-card-title class="d-flex align-center justify-space-between">
          <span>Violation Detail</span>
          <v-btn icon="mdi-close" variant="text" @click="detail = false" />
        </v-card-title>
        <v-alert v-if="selected.finding_summary" type="info" variant="tonal"
                 density="compact" class="mt-2" icon="mdi-robot-outline">
          {{ selected.finding_summary }}
        </v-alert>
        <v-list density="compact" class="mt-2">
          <v-list-item title="Violation ID" :subtitle="selected.violation_id" />
          <v-list-item title="City" :subtitle="selected.city" />
          <v-list-item title="Domain" :subtitle="selected.domain" />
          <v-list-item title="Rule" :subtitle="selected.rule_id" />
          <v-list-item title="Citation" :subtitle="selected.citation" />
          <v-list-item title="Severity" :subtitle="selected.severity" />
          <v-list-item title="AI System" :subtitle="selected.vendor_display_name || selected.vendor_id" />
          <v-list-item title="Asset Type" :subtitle="selected.asset_type || '—'" />
          <v-list-item title="Matched Signatures"
                       :subtitle="(selected.matched_signals && selected.matched_signals.length) ? selected.matched_signals.join(', ') : '—'" />
          <v-list-item title="Vendor ID" :subtitle="selected.vendor_id" />
          <v-list-item title="Status" :subtitle="selected.status" />
          <v-list-item title="First Observed" :subtitle="fmtDate(selected.first_observed_utc)" />
          <v-list-item title="Cure Deadline" :subtitle="fmtDate(selected.cure_deadline_utc)" />
          <v-list-item title="Days Remaining" :subtitle="String(liveDaysLeft(selected.cure_deadline_utc) ?? selected.days_remaining ?? '—')" />
        </v-list>
        <v-divider class="my-3" />
        <div class="text-subtitle-2 mb-1">Evidence / Remediation</div>
        <pre class="text-caption overflow-auto"
             style="max-height:200px;white-space:pre-wrap">{{ JSON.stringify(selected.evidence, null, 2) }}</pre>
      </v-card>
    </v-navigation-drawer>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useViolationsStore } from '../stores/violations'
import ComplianceStatusChip from '../components/ComplianceStatusChip.vue'
import CurePeriodGauge from '../components/CurePeriodGauge.vue'
import { liveDaysLeft } from '../utils/cure'

const vStore = useViolationsStore()
const statusFilter = ref(null)
const selected     = ref(null)
const detail       = ref(false)

const filtered = computed(() => {
  if (!statusFilter.value) return vStore.items
  return vStore.items.filter(v => v.status === statusFilter.value)
})

const toggleFilter = (s) => { statusFilter.value = statusFilter.value === s ? null : s }

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—'

const severityColor = (s) => ({ high: 'error', medium: 'warning', low: 'info' }[s] || 'default')

async function refresh() { await vStore.fetchViolations() }

onMounted(refresh)
</script>
