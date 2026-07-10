<template>
  <v-dialog v-model="open" max-width="880" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-file-document-multiple-outline</v-icon>
        Import Procurement / Contracts
        <v-spacer />
        <v-chip size="small" color="teal" variant="tonal" prepend-icon="mdi-shield-account">
          Admin
        </v-chip>
      </v-card-title>

      <v-card-text>
        <!-- Step 1: file selection -->
        <template v-if="phase === 'select'">
          <p class="text-body-2 mb-3">
            Upload a vendor / spend / contract CSV with a <code>vendor</code> column
            (optional: <code>city, contract_id, amount, term, department</code>).
            Each vendor is matched against the AI tool catalog; confident matches are
            added to the AI Inventory as <strong>procured AI</strong>. Non-AI vendors
            are skipped. Nothing is scanned; no financial totals are stored.
          </p>
          <v-text-field
            v-model="defaultCityInput"
            label="Default city (used when a row has no city column)"
            density="comfortable"
            prepend-icon="mdi-city"
            :placeholder="defaultCity || 'e.g. City of Lewisville'"
            clearable
          />
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

        <!-- Step 2: preview -->
        <template v-else-if="phase === 'preview'">
          <v-alert :type="invalidCount ? 'warning' : 'info'" variant="tonal" class="mb-3" density="compact">
            {{ validRows.length }} row{{ validRows.length === 1 ? '' : 's' }} will be checked against the AI
            catalog<span v-if="invalidCount">, {{ invalidCount }} skipped (missing vendor or city)</span>.
            The server decides which are AI and reports matches.
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
            Matched <strong>{{ result.matched }}</strong> AI vendor{{ result.matched === 1 ? '' : 's' }}
            of {{ result.rows }} rows; <strong>{{ result.written }}</strong> added/updated in the inventory.
            <span v-if="result.skipped"> {{ result.skipped }} row{{ result.skipped === 1 ? '' : 's' }} skipped (not AI or missing fields).</span>
          </v-alert>
          <template v-if="result.cities?.length">
            <div class="text-subtitle-2 mb-1">Cities updated</div>
            <v-chip-group>
              <v-chip v-for="c in result.cities" :key="c" size="small" variant="tonal">{{ c }}</v-chip>
            </v-chip-group>
          </template>
          <v-alert v-if="result.errors?.length" type="warning" variant="tonal" density="compact" class="mt-3">
            {{ result.errors.length }} row(s) failed to write: {{ result.errors.slice(0, 5).join('; ') }}
          </v-alert>
          <p class="text-body-2 mt-3 text-medium-emphasis">
            New assets appear as <strong>Needs attestation</strong> — a human confirms owner and purpose.
            A vendor already found by a scan or Sentinel now lists procurement as an additional source.
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
          :loading="store.running"
          :disabled="!validRows.length"
          @click="doImport"
        >
          Check {{ validRows.length }} row{{ validRows.length === 1 ? '' : 's' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
/**
 * ProcurementImportDialog — admin CSV import of vendor/spend/contract rows into
 * the procurement discovery channel. The client parses + previews so the admin
 * sees what will be checked; the SERVER matches against the AI tool catalog and
 * reports which vendors were AI (never trust the client for the match decision).
 *
 * Mirrors BulkImportDialog's parse/preview UX (project consistency).
 */
import { ref, computed } from 'vue'
import { useDiscoveryStore } from '../stores/discovery'
import { useInventoryStore } from '../stores/inventory'

const open  = defineModel({ type: Boolean, default: false })
const props = defineProps({
  /** Pre-fill the default city (e.g. the embedded city page). */
  defaultCity: { type: String, default: '' },
})
const emit = defineEmits(['done'])

const store     = useDiscoveryStore()
const inventory = useInventoryStore()

const phase           = ref('select')   // 'select' | 'preview' | 'done'
const file            = ref(null)
const defaultCityInput = ref(props.defaultCity || '')
const parsedRows      = ref([])
const parseError      = ref('')
const importError     = ref('')
const result          = ref({})

const previewHeaders = [
  { title: '#',        key: '_line',       sortable: false },
  { title: 'Vendor',   key: 'vendor',      sortable: false },
  { title: 'City',     key: 'city',        sortable: false },
  { title: 'Contract', key: 'contract_id', sortable: false },
  { title: 'Status',   key: '_status',     sortable: false },
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

  const header = raw[0].map(h => h.trim().toLowerCase())
  const col = (name) => header.indexOf(name)
  // Accept vendor | supplier | vendor_name for the vendor column.
  const vendorCol = ['vendor', 'supplier', 'vendor_name'].map(col).find(i => i !== -1)
  if (vendorCol === undefined || vendorCol === -1) {
    parseError.value = 'Header row must include a "vendor" (or "supplier") column'
    return
  }
  const fallbackCity = (defaultCityInput.value || props.defaultCity || '').trim()

  parsedRows.value = raw.slice(1).map((cells, i) => {
    const get = (name) => (col(name) === -1 ? '' : (cells[col(name)] || '').trim())
    const vendor = (cells[vendorCol] || '').trim()
    const city   = get('city') || fallbackCity
    const rowObj = {
      _line: i + 2,
      vendor,
      city,
      contract_id: get('contract_id') || get('contract'),
      amount:      get('amount'),
      term:        get('term'),
      department:  get('department') || get('dept'),
      _error: '',
    }
    if (!vendor) rowObj._error = 'missing vendor'
    else if (!city) rowObj._error = 'no city (add a city column or set a default city)'
    return rowObj
  })
  if (!parsedRows.value.length) { parseError.value = 'No data rows found'; return }
  phase.value = 'preview'
}

async function doImport() {
  importError.value = ''
  try {
    result.value = await store.runProcurement(
      validRows.value.map(({ _line, _error, ...clean }) => clean),
      { default_city: (defaultCityInput.value || props.defaultCity || '').trim() || undefined },
    )
    phase.value = 'done'
    // Refresh the shared inventory so new procured assets appear in the panel.
    try { await inventory.fetchInventory(props.defaultCity || null) } catch { /* non-fatal */ }
    emit('done', result.value)
  } catch (e) {
    importError.value = e.response?.status === 403
      ? 'Procurement discovery is restricted to administrators.'
      : (e.response?.data?.detail || e.message)
  }
}

function downloadTemplate() {
  const csv = 'vendor,city,contract_id,amount,term,department\n'
    + 'OpenAI,City of Lewisville,C-2026-014,,annual,IT\n'
    + 'Otter.ai,City of Lewisville,C-2026-051,,annual,Clerk\n'
    + 'Acme Plumbing,City of Lewisville,C-2026-077,,,Facilities\n'
  const a = document.createElement('a')
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  a.download = 'procurement_import_template.csv'
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
  setTimeout(reset, 300)
  result.value = {}
}
</script>
