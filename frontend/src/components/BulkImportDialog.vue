<template>
  <v-dialog v-model="open" max-width="860" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-upload-multiple</v-icon>
        Bulk Import Cities
        <v-spacer />
        <v-chip size="small" color="primary" variant="tonal" prepend-icon="mdi-shield-account">
          Platform Admin
        </v-chip>
      </v-card-title>

      <v-card-text>
        <!-- Step 1: file selection -->
        <template v-if="phase === 'select'">
          <p class="text-body-2 mb-3">
            Upload a CSV with columns <code>city, domain</code>
            (optional: <code>url, jurisdiction, tags, cloudflare_protected, population</code>).
            Imported cities are created as <strong>Not Assessed</strong> and are
            <strong>not scanned automatically</strong> — run a scan when you're ready.
          </p>
          <v-file-input
            v-model="file"
            label="Select CSV file"
            accept=".csv,text/csv"
            prepend-icon="mdi-file-delimited"
            density="comfortable"
            :error-messages="parseError"
            @update:model-value="onFile"
          />
          <v-btn variant="text" size="small" prepend-icon="mdi-download"
                 class="mt-1" @click="downloadTemplate">
            Download CSV template
          </v-btn>
        </template>

        <!-- Step 2: preview + validate -->
        <template v-else-if="phase === 'preview'">
          <v-alert :type="invalidCount ? 'warning' : 'success'" variant="tonal" class="mb-3" density="compact">
            {{ validRows.length }} row{{ validRows.length === 1 ? '' : 's' }} ready to import<span v-if="invalidCount">,
            {{ invalidCount }} will be skipped (shown below)</span>.
          </v-alert>
          <v-data-table
            :headers="previewHeaders"
            :items="parsedRows"
            density="compact"
            :items-per-page="10"
            item-value="_line"
          >
            <template #item._status="{ item }">
              <v-chip v-if="item._error" size="x-small" color="error" label>{{ item._error }}</v-chip>
              <v-chip v-else size="x-small" color="success" label>ok</v-chip>
            </template>
          </v-data-table>
        </template>

        <!-- Step 3: server result -->
        <template v-else-if="phase === 'done'">
          <v-alert type="success" variant="tonal" class="mb-3">
            Imported <strong>{{ result.added }}</strong> of {{ result.total_submitted }} submitted cities.
          </v-alert>
          <template v-if="result.skipped?.length">
            <div class="text-subtitle-2 mb-1">Skipped by server ({{ result.skipped.length }})</div>
            <v-table density="compact">
              <thead><tr><th>Row</th><th>City</th><th>Reason</th></tr></thead>
              <tbody>
                <tr v-for="s in result.skipped" :key="s.row">
                  <td>{{ s.row }}</td><td>{{ s.city }}</td><td>{{ s.reason }}</td>
                </tr>
              </tbody>
            </v-table>
          </template>
          <p class="text-body-2 mt-3 text-medium-emphasis">
            Imported cities appear on the dashboard as <strong>Not Assessed</strong>.
            Use Run Audit when you're ready to scan them.
          </p>
        </template>

        <v-alert v-if="importError" type="error" variant="tonal" class="mt-3" density="compact">
          {{ importError }}
        </v-alert>
      </v-card-text>

      <v-card-actions>
        <v-btn v-if="phase === 'preview'" variant="text" @click="reset">Back</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="close">{{ phase === 'done' ? 'Close' : 'Cancel' }}</v-btn>
        <v-btn
          v-if="phase === 'preview'"
          color="primary"
          :loading="importing"
          :disabled="!validRows.length"
          @click="doImport"
        >
          Import {{ validRows.length }} cit{{ validRows.length === 1 ? 'y' : 'ies' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
/**
 * BulkImportDialog — platform_admin-only CSV import of audit targets.
 *
 * Client parses + pre-validates so the admin sees exactly what will happen
 * BEFORE anything writes; the server re-validates and dedupes authoritatively
 * (never trust the client). Import never triggers scans (proxy-cost control).
 */
import { ref, computed } from 'vue'
import { useTargetsStore } from '../stores/targets'

const open = defineModel({ type: Boolean, default: false })
const store = useTargetsStore()

const phase       = ref('select')   // 'select' | 'preview' | 'done'
const file        = ref(null)
const parsedRows  = ref([])
const parseError  = ref('')
const importing   = ref(false)
const importError = ref('')
const result      = ref({})

const previewHeaders = [
  { title: '#',            key: '_line',        sortable: false },
  { title: 'City',         key: 'city',         sortable: false },
  { title: 'Domain',       key: 'domain',       sortable: false },
  { title: 'Jurisdiction', key: 'jurisdiction', sortable: false },
  { title: 'Population',   key: 'population',    sortable: false },
  { title: 'Status',       key: '_status',      sortable: false },
]

const validRows    = computed(() => parsedRows.value.filter(r => !r._error))
const invalidCount = computed(() => parsedRows.value.length - validRows.value.length)

/** Minimal RFC-4180-ish CSV parser: quoted fields, embedded commas/quotes. */
function parseCsv(text) {
  const rows = []
  let row = [], field = '', inQuotes = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++ }
      else if (c === '"') inQuotes = false
      else field += c
    } else if (c === '"') inQuotes = true
    else if (c === ',') { row.push(field); field = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(field); field = ''
      if (row.some(f => f.trim() !== '')) rows.push(row)
      row = []
    } else field += c
  }
  row.push(field)
  if (row.some(f => f.trim() !== '')) rows.push(row)
  return rows
}

const TRUTHY = new Set(['true', '1', 'yes', 'y'])

async function onFile(f) {
  parseError.value = ''
  const theFile = Array.isArray(f) ? f[0] : f
  if (!theFile) return
  let text
  try {
    text = await theFile.text()
  } catch {
    parseError.value = 'Could not read file'
    return
  }
  const raw = parseCsv(text)
  if (!raw.length) { parseError.value = 'File is empty'; return }

  // Header row: map column names → indexes (case-insensitive, required: city, domain)
  const header = raw[0].map(h => h.trim().toLowerCase())
  const col = (name) => header.indexOf(name)
  if (col('city') === -1 || col('domain') === -1) {
    parseError.value = 'Header row must include "city" and "domain" columns'
    return
  }

  const seen = new Set()
  parsedRows.value = raw.slice(1).map((cells, i) => {
    const get = (name) => (col(name) === -1 ? '' : (cells[col(name)] || '').trim())
    const city   = get('city')
    const domain = get('domain').toLowerCase().replace(/^https?:\/\//, '').split('/')[0]
    const rowObj = {
      _line: i + 2,   // 1-based + header row
      city,
      domain,
      url: get('url'),
      jurisdiction: get('jurisdiction') || 'TX',
      tags: get('tags') ? get('tags').split(';').map(t => t.trim()).filter(Boolean) : [],
      cloudflare_protected: TRUTHY.has(get('cloudflare_protected').toLowerCase()),
      population: get('population') ? Number(get('population').replace(/[,\s]/g, '')) || 0 : 0,
      _error: '',
    }
    if (!city || !domain) rowObj._error = 'missing city or domain'
    else if (!domain.includes('.')) rowObj._error = 'invalid domain'
    else if (seen.has(city.toLowerCase())) rowObj._error = 'duplicate in file'
    else seen.add(city.toLowerCase())
    return rowObj
  })
  if (!parsedRows.value.length) { parseError.value = 'No data rows found'; return }
  phase.value = 'preview'
}

async function doImport() {
  importing.value = true
  importError.value = ''
  try {
    result.value = await store.bulkImport(
      validRows.value.map(({ _line, _error, ...clean }) => clean),
    )
    phase.value = 'done'
  } catch (e) {
    importError.value = e.response?.status === 403
      ? 'Bulk import is restricted to platform administrators.'
      : (e.response?.data?.detail || e.message)
  } finally {
    importing.value = false
  }
}

function downloadTemplate() {
  const csv = 'city,domain,url,jurisdiction,tags,cloudflare_protected,population\n'
    + 'Grand Prairie,gptx.org,https://www.gptx.org,TX,dfw;pilot,false,196000\n'
    + 'Denton,cityofdenton.com,,TX,dfw,true,148000\n'
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  a.download = 'bulk_import_template.csv'
  a.click()
  URL.revokeObjectURL(a.href)
}

function reset() {
  phase.value = 'select'
  file.value = null
  parsedRows.value = []
  parseError.value = ''
  importError.value = ''
}

function close() {
  open.value = false
  setTimeout(reset, 300)   // reset after the close animation
  result.value = {}
}
</script>
