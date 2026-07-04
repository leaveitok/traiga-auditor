<template>
  <v-container fluid class="pa-6">
    <!-- Header row -->
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Compliance Dashboard</div>
        <div class="text-caption text-medium-emphasis">
          Texas HB 149 / TRAIGA · Tex. Bus. &amp; Com. Code Ch. 552
        </div>
      </div>
      <div class="d-flex align-center ga-2 flex-wrap">
        <!-- Scheduler status indicator -->
        <v-tooltip
          v-if="auditStore.scheduleStatus"
          :text="auditStore.scheduleStatus.scheduler_running
            ? `Auto-scan every ${auditStore.scheduleStatus.scan_cadence_hours}h · next: ${fmtDate(auditStore.scheduleStatus.next_run_utc) || 'calculating...'}`
            : 'Scheduler not running'"
          location="bottom"
        >
          <template #activator="{ props }">
            <v-chip
              v-bind="props"
              :color="auditStore.scheduleStatus.scheduler_running ? 'success' : 'warning'"
              variant="tonal" size="small" label
            >
              <v-icon start>{{ auditStore.scheduleStatus.scheduler_running ? 'mdi-clock-check-outline' : 'mdi-clock-alert-outline' }}</v-icon>
              {{ auditStore.scheduleStatus.auto_scan_cities }} auto
              <span v-if="auditStore.scheduleStatus.manual_scan_cities > 0">
                &nbsp;· {{ auditStore.scheduleStatus.manual_scan_cities }} manual
              </span>
            </v-chip>
          </template>
        </v-tooltip>

        <!-- Add City button — opens AddCityDialog, then refreshes scorecard -->
        <v-btn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-plus"
          size="small"
          @click="addCityDialog = true"
        >
          Add City
        </v-btn>

        <AuditRunButton @audit-complete="refresh" />
      </div>
    </div>

    <!-- Summary KPI cards -->
    <v-row class="mb-4">
      <v-col v-for="kpi in kpis" :key="kpi.label" cols="6" sm="4" md="2">
        <v-card :color="kpi.color" variant="tonal" class="text-center pa-4">
          <div class="text-h4 font-weight-bold">{{ kpi.value }}</div>
          <div class="text-caption font-weight-medium">{{ kpi.label }}</div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Scorecard table -->
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>City Compliance Scorecard</span>
        <v-btn icon="mdi-refresh" variant="text" :loading="store.loading"
               @click="refresh" />
      </v-card-title>

      <v-alert v-if="store.error" type="error" class="ma-4">{{ store.error }}</v-alert>

      <v-data-table
        :headers="headers"
        :items="store.rows"
        :loading="store.loading"
        item-value="city"
        hover
        class="elevation-0"
        @click:row="(_, { item }) => $router.push(`/city/${encodeURIComponent(item.city)}`)"
        style="cursor: pointer"
      >
        <template #item.traiga_status="{ item }">
          <ComplianceStatusChip :status="item.traiga_status" />
        </template>

        <template #item.compliance_score="{ item }">
          <v-chip :color="bandColor(item.band)" label size="small" class="font-weight-bold">
            {{ item.compliance_score }}
          </v-chip>
        </template>

        <template #item.min_days_remaining="{ item }">
          <CurePeriodGauge :days="parseMinDays(item.min_days_remaining)"
                           :size="44" />
        </template>

        <template #item.open_violations_count="{ item }">
          <v-chip :color="item.open_violations_count > 0 ? 'error' : 'success'"
                  variant="tonal" size="small">
            {{ item.open_violations_count }}
          </v-chip>
        </template>

        <template #item.city="{ item }">
          <span class="text-primary font-weight-medium" style="text-decoration: underline dotted">
            {{ item.city }}
          </span>
        </template>

        <template #item.cloudflare_protected="{ item }">
          <v-chip
            v-if="item.cloudflare_protected"
            color="warning" variant="tonal" size="x-small" label
            title="Cloudflare-protected — requires manual Deep Scan"
          >
            <v-icon start size="12">mdi-shield-alert-outline</v-icon>
            Manual Scan
          </v-chip>
          <v-chip v-else color="success" variant="tonal" size="x-small" label>
            <v-icon start size="12">mdi-robot-outline</v-icon>
            Auto
          </v-chip>
        </template>

        <template #item.last_scanned_utc="{ item }">
          <span class="text-caption text-medium-emphasis">
            {{ fmtDate(item.last_scanned_utc) }}
          </span>
        </template>

        <template #item.actions="{ item }">
          <v-tooltip :text="item.traiga_status === 'not_assessed' ? 'Run audit first' : 'Generate Compliance Report'" location="top">
            <template #activator="{ props }">
              <span v-bind="props">
                <v-btn
                  size="small" variant="text" color="primary"
                  :loading="rStore.isGenerating(item.city)"
                  :disabled="item.traiga_status === 'not_assessed'"
                  @click.stop="downloadReport(item.city)"
                >
                  <v-icon start>mdi-file-document-outline</v-icon>
                  Report
                </v-btn>
              </span>
            </template>
          </v-tooltip>
        </template>
      </v-data-table>

      <!-- Report generation snackbar -->
      <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="4000" location="bottom right">
        {{ snackbar.text }}
      </v-snackbar>
    </v-card>

    <!-- Add City Dialog -->
    <AddCityDialog v-model="addCityDialog" @added="refresh" />
  </v-container>
</template>

<script setup>
import { onMounted, computed, watch, ref, reactive } from 'vue'
import { useScorecardStore } from '../stores/scorecard'
import { useAuditStore } from '../stores/audit'
import AuditRunButton from '../components/AuditRunButton.vue'
import ComplianceStatusChip from '../components/ComplianceStatusChip.vue'
import CurePeriodGauge from '../components/CurePeriodGauge.vue'
import AddCityDialog from '../components/AddCityDialog.vue'
import { useReportsStore } from '../stores/reports'

const store      = useScorecardStore()
const auditStore = useAuditStore()
const rStore     = useReportsStore()
const snackbar   = reactive({ show: false, text: '', color: 'success' })
const addCityDialog = ref(false)

// Auto-refresh scorecard when an audit finishes
watch(() => auditStore.status, (newStatus) => {
  if (newStatus === 'completed') refresh()
})

const headers = [
  { title: 'City',            key: 'city',                  sortable: true  },
  { title: 'Jurisdiction',    key: 'jurisdiction',          sortable: true  },
  { title: 'TRAIGA Status',   key: 'traiga_status',         sortable: true  },
  { title: 'Score',           key: 'compliance_score',      sortable: true  },
  { title: 'Open Violations', key: 'open_violations_count', sortable: true  },
  { title: 'Min Days Left',   key: 'min_days_remaining',    sortable: true  },
  { title: 'Scan Type',       key: 'cloudflare_protected',  sortable: false },
  { title: 'Last Scanned',    key: 'last_scanned_utc',      sortable: true  },
  { title: 'Report',          key: 'actions',               sortable: false },
]

async function downloadReport(city) {
  const ok = await rStore.download(city)
  snackbar.text  = ok ? `Report downloaded for ${city}` : `Report failed: ${rStore.error}`
  snackbar.color = ok ? 'success' : 'error'
  snackbar.show  = true
}

const kpis = computed(() => {
  const s = store.summary
  if (!s) return []
  return [
    { label: 'Total Cities',  value: s.total_cities,  color: 'primary' },
    { label: 'Compliant',     value: s.compliant,     color: 'success' },
    { label: 'In Cure',       value: s.in_cure,       color: 'warning' },
    { label: 'Non-Compliant', value: s.non_compliant, color: 'error'   },
    { label: 'Expired',       value: s.expired,       color: 'error'   },
    { label: 'Avg Score',     value: s.average_compliance_score ?? '—', color: 'info' },
  ]
})

const bandColor = (band) => ({ green: 'success', amber: 'warning', red: 'error' }[band] || 'default')

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : '—'

const parseMinDays = (val) => {
  if (!val || val === 'None' || val === '') return null
  const n = Number(val)
  return isNaN(n) ? null : n
}

async function refresh() { await store.fetchScorecard() }

onMounted(() => {
  refresh()
  auditStore.fetchScheduleStatus()
})
</script>
