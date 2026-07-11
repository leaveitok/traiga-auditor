<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Audit Log</div>
        <div class="text-caption text-medium-emphasis">
          Append-only evidence trail — scans, configuration changes, and administrative actions
        </div>
      </div>
      <v-btn icon="mdi-refresh" variant="outlined" @click="load" />
    </div>

    <v-card>
      <v-data-table
        :headers="headers"
        :items="rows"
        :loading="loading"
        item-value="timestamp_utc"
        hover
        density="compact"
      >
        <template #item.timestamp_utc="{ item }">
          <span class="text-caption">{{ fmtDate(item.timestamp_utc) }}</span>
        </template>
        <template #item._actor="{ item }">
          <v-chip size="x-small" :color="item._actor === 'system' ? 'grey' : 'primary'"
                  variant="tonal" label>{{ item._actor }}</v-chip>
        </template>
        <template #item._summary="{ item }">
          <span class="text-caption">{{ item._summary }}</span>
        </template>
        <template #item.failures="{ item }">
          <v-chip :color="Number(item.failures) > 0 ? 'error' : 'success'"
                  size="x-small" label>{{ item.failures }}</v-chip>
        </template>
        <template #item.details="{ item }">
          <v-btn size="x-small" variant="text" icon="mdi-code-json"
                 @click="showDetails(item)" />
        </template>
      </v-data-table>
    </v-card>

    <v-dialog v-model="detailDialog" max-width="480">
      <v-card>
        <v-card-title>Log Entry Details</v-card-title>
        <v-card-text>
          <pre class="text-caption" style="white-space:pre-wrap">{{ JSON.stringify(detailItem, null, 2) }}</pre>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="detailDialog = false">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useLogsStore } from '../stores/logs'

const store        = useLogsStore()
const detailDialog = ref(false)
const detailItem   = ref(null)

const headers = [
  { title: 'Timestamp',    key: 'timestamp_utc', sortable: true  },
  { title: 'Event',        key: 'event',         sortable: true  },
  { title: 'Actor',        key: '_actor',        sortable: true  },
  { title: 'Summary',      key: '_summary',      sortable: false },
  { title: 'Cities',       key: 'city_count',    sortable: true  },
  { title: 'Failures',     key: 'failures',      sortable: true  },
  { title: 'Details',      key: 'details',       sortable: false },
]

/** The backend returns details already parsed (object); tolerate legacy details_json. */
function enrich(row) {
  const d = row.details || (() => {
    try { return JSON.parse(row.details_json || '{}') } catch { return {} }
  })()
  return { ...row, details: d, _actor: d.actor || 'system', _summary: d.summary || '' }
}

const rows    = computed(() => store.rows.map(enrich))
const loading = computed(() => store.loading)

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString() : '—'

function showDetails(item) {
  detailItem.value   = item
  detailDialog.value = true
}

onMounted(() => store.fetchLogs(200))
</script>
