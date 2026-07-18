<template>
  <v-container fluid class="pa-3 pa-sm-6">
    <div class="d-flex align-center mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Error Log</div>
        <div class="text-caption text-medium-emphasis">
          Operational failures across the audit pipeline, scheduler, and deep scans — platform admin only
        </div>
      </div>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" :loading="store.loading" @click="store.fetch()" />
    </div>

    <v-alert v-if="store.error" type="warning" variant="tonal" density="compact" class="mb-4">
      {{ store.error }}
    </v-alert>

    <v-alert
      v-else-if="!store.loading && !store.entries.length"
      type="success" variant="tonal" density="compact" class="mb-4"
      text="No errors recorded. When a scan, scheduled run, or deep scan fails, it will appear here."
    />

    <v-card v-if="store.entries.length">
      <v-data-table
        :headers="headers"
        :items="store.entries"
        :loading="store.loading"
        density="comfortable"
        item-value="_idx"
        show-expand
        :items-per-page="25"
      >
        <template #item.level="{ item }">
          <v-chip :color="levelColor(item.level)" size="small" variant="flat" label>
            {{ (item.level || 'error').toUpperCase() }}
          </v-chip>
        </template>
        <template #item.timestamp_utc="{ item }">
          <span class="text-no-wrap text-caption">{{ fmt(item.timestamp_utc) }}</span>
        </template>
        <template #item.source="{ item }">
          <code class="text-caption">{{ item.source }}</code>
        </template>
        <template #item.city="{ item }">
          <span>{{ item.city || '—' }}</span>
        </template>
        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-4 bg-grey-lighten-4">
              <div v-if="item.details?.ref" class="mb-2 text-caption">
                <strong>Reference:</strong> <code>{{ item.details.ref }}</code>
              </div>
              <div class="text-caption text-medium-emphasis mb-1">Traceback / context</div>
              <pre class="traceback">{{ item.details?.traceback || detailsFallback(item) }}</pre>
            </td>
          </tr>
        </template>
      </v-data-table>
    </v-card>
  </v-container>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useErrorsStore } from '../stores/errors'

const baseStore = useErrorsStore()
// Stable per-row key for the data table expander.
const store = {
  get loading() { return baseStore.loading },
  get error()   { return baseStore.error },
  get entries() { return baseStore.entries.map((e, i) => ({ ...e, _idx: i })) },
  fetch: (...a) => baseStore.fetch(...a),
}

const headers = [
  { title: 'When', key: 'timestamp_utc', width: 180 },
  { title: 'Level', key: 'level', width: 110 },
  { title: 'Source', key: 'source', width: 160 },
  { title: 'Message', key: 'message' },
  { title: 'City', key: 'city', width: 120 },
  { title: '', key: 'data-table-expand' },
]

const levelColor = (l) => ({ error: 'error', warning: 'amber-darken-2', info: 'blue-grey' }[l] || 'error')

const fmt = (ts) => {
  if (!ts) return '—'
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString()
}

const detailsFallback = (item) => {
  const d = item.details || {}
  const keys = Object.keys(d)
  return keys.length ? JSON.stringify(d, null, 2) : 'No additional detail captured.'
}

onMounted(() => baseStore.fetch())
</script>

<style scoped>
.traceback {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.4;
  max-height: 320px;
  overflow: auto;
  margin: 0;
}
</style>
