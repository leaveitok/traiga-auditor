<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-2 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Sentinel — Internal AI DLP</div>
        <div class="text-caption text-medium-emphasis">
          Browser-level blocks of PII / CJI / PHI entering AI tools · metadata only — detected content never leaves the employee's browser
        </div>
      </div>
      <v-btn icon="mdi-refresh" variant="text" @click="refresh" />
    </div>

    <v-alert type="info" variant="tonal" density="compact" class="mb-4" icon="mdi-shield-lock-outline">
      Internal personnel data — restricted to admin / security roles. Not part of the external transparency scorecard.
    </v-alert>

    <v-alert v-if="store.error" type="error" class="mb-4">{{ store.error }}</v-alert>

    <!-- KPI row -->
    <v-row v-if="store.summary" class="mb-2">
      <v-col v-for="kpi in kpis" :key="kpi.label" cols="6" md="3">
        <v-card :color="kpi.color" variant="tonal">
          <v-card-text>
            <div class="text-h4 font-weight-bold">{{ kpi.value }}</div>
            <div class="text-caption">{{ kpi.label }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Silent devices (tamper canary) -->
    <v-alert v-if="store.silentDevices.length" type="warning" variant="tonal" class="mb-4"
             icon="mdi-lan-disconnect">
      {{ store.silentDevices.length }} device(s) with no Sentinel heartbeat —
      investigate possible bypass (unmanaged browser, disabled agent):
      {{ store.silentDevices.map(d => d.device_id).join(', ') }}
    </v-alert>

    <!-- Events table -->
    <v-card class="mb-6">
      <v-card-title class="text-subtitle-1">Recent Events</v-card-title>
      <v-data-table
        :headers="eventHeaders"
        :items="store.events"
        :loading="store.loading"
        density="compact"
        items-per-page="25"
      >
        <template #item.timestamp_utc="{ item }">{{ fmtDate(item.timestamp_utc) }}</template>
        <template #item.action_taken="{ item }">
          <v-chip size="x-small" :color="item.action_taken === 'blocked' ? 'error' : 'warning'" label>
            {{ item.action_taken }}
          </v-chip>
        </template>
        <template #item.detections="{ item }">
          <v-chip v-for="d in item.detections" :key="d.policy_id + d.pattern_id"
                  size="x-small" class="mr-1" color="primary" variant="tonal" label>
            {{ d.policy_id }} ×{{ d.match_count }}
          </v-chip>
        </template>
      </v-data-table>
    </v-card>

    <!-- Device health -->
    <v-card>
      <v-card-title class="text-subtitle-1">Device Heartbeats</v-card-title>
      <v-data-table
        :headers="deviceHeaders"
        :items="store.devices"
        :loading="store.loading"
        density="compact"
      >
        <template #item.silent="{ item }">
          <v-chip size="x-small" :color="item.silent ? 'error' : 'success'" label>
            {{ item.silent ? 'SILENT' : 'reporting' }}
          </v-chip>
        </template>
        <template #item.last_heartbeat_utc="{ item }">{{ fmtDate(item.last_heartbeat_utc) }}</template>
      </v-data-table>
    </v-card>
  </v-container>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useSentinelStore } from '../stores/sentinel'

const store = useSentinelStore()

const kpis = computed(() => [
  { label: 'Total Events',      value: store.summary.total_events,      color: 'primary' },
  { label: 'Blocked',           value: store.summary.blocked,           color: 'error' },
  { label: 'Devices Reporting', value: store.summary.devices_reporting, color: 'success' },
  { label: 'Devices Silent',    value: store.summary.devices_silent,    color: store.summary.devices_silent ? 'warning' : 'success' },
])

const eventHeaders = [
  { title: 'Time',    key: 'timestamp_utc' },
  { title: 'User',    key: 'user_id' },
  { title: 'Device',  key: 'device_id' },
  { title: 'App',     key: 'site_id' },
  { title: 'Trigger', key: 'trigger' },
  { title: 'Policies', key: 'detections', sortable: false },
  { title: 'Action',  key: 'action_taken' },
]

const deviceHeaders = [
  { title: 'Device',         key: 'device_id' },
  { title: 'User',           key: 'user_id' },
  { title: 'Last Heartbeat', key: 'last_heartbeat_utc' },
  { title: 'Ruleset',        key: 'ruleset_version' },
  { title: 'Status',         key: 'status' },
  { title: 'Health',         key: 'silent' },
]

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString() : '—'

async function refresh() { await store.fetchAll() }
onMounted(refresh)
</script>
