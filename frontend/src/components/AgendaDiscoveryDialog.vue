<template>
  <v-dialog v-model="open" max-width="720" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-gavel</v-icon>
        Discover AI from Council Agendas
        <v-spacer />
        <v-chip size="small" color="indigo" variant="tonal" prepend-icon="mdi-shield-account">Admin</v-chip>
      </v-card-title>

      <v-card-text>
        <template v-if="phase !== 'done'">
          <p class="text-body-2 mb-3">
            Scans a city's council / EDC agendas for awarded tech contracts and adds any
            AI to the inventory as <strong>procured (agenda)</strong>. Zoning &amp; advisory
            meetings are skipped. Findings are candidates for human review.
          </p>

          <v-select
            v-model="source" :items="sourceOptions" item-title="label" item-value="value"
            label="Agenda source" density="comfortable" prepend-icon="mdi-source-branch" />

          <v-text-field v-if="source === 'legistar'" v-model="legistarClient"
            label="Legistar client slug" placeholder="cityoflewisville"
            hint="From the portal URL: <slug>.legistar.com" persistent-hint
            density="comfortable" prepend-icon="mdi-web" class="mb-2" />
          <v-text-field v-else-if="source === 'pdf'" v-model="pdfUrl"
            label="Agenda PDF URL" placeholder="https://agenda.city.gov/.../Agenda.pdf"
            density="comfortable" prepend-icon="mdi-file-pdf-box" class="mb-2" />
          <v-textarea v-else v-model="agendaText"
            label="Paste agenda text" rows="5" auto-grow
            density="comfortable" prepend-icon="mdi-text" class="mb-2" />

          <div class="d-flex ga-3" v-if="source === 'legistar'">
            <v-text-field v-model="since" label="From" type="date" density="comfortable"
              prepend-icon="mdi-calendar-start" />
            <v-text-field v-model="until" label="To" type="date" density="comfortable"
              prepend-icon="mdi-calendar-end" />
          </div>
          <div v-if="source === 'legistar'" class="text-caption text-medium-emphasis">
            Date range applies to the meeting list before any extraction (cost control).
          </div>

          <v-alert v-if="runError" :type="disabled ? 'info' : 'error'" variant="tonal"
                   density="compact" class="mt-3">{{ runError }}</v-alert>
        </template>

        <template v-else>
          <v-alert type="success" variant="tonal" class="mb-2">
            Matched <strong>{{ result.matched }}</strong>,
            <strong>{{ result.candidates || 0 }}</strong> flagged for review,
            <strong>{{ result.written }}</strong> added/updated
            <span v-if="result.rows"> from {{ result.rows }} gated item(s)</span>.
          </v-alert>

          <!-- Which extractor actually ran — makes the silent Vertex→keyword
               fail-open visible in-app (no GCP log access needed). -->
          <v-chip v-if="result.extractor" size="small" label
                  variant="tonal" :color="extractorMeta.color"
                  :prepend-icon="extractorMeta.icon" class="mb-2">
            {{ extractorMeta.label }}
          </v-chip>

          <v-chip-group v-if="result.cities?.length">
            <v-chip v-for="c in result.cities" :key="c" size="small" variant="tonal">{{ c }}</v-chip>
          </v-chip-group>
          <p class="text-body-2 mt-3 text-medium-emphasis">
            New items appear as <strong>Needs attestation</strong> for a human to confirm.
          </p>
        </template>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">{{ phase === 'done' ? 'Close' : 'Cancel' }}</v-btn>
        <v-btn v-if="phase !== 'done'" color="primary" :loading="store.running"
               :disabled="!canRun" @click="run">Scan agendas</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
/**
 * AgendaDiscoveryDialog — admin trigger for council-agenda discovery. Obeys
 * components → stores → GovernanceService layering. The engine is flag-gated
 * server-side; a 503 is surfaced as an informational message.
 */
import { ref, computed } from 'vue'
import { useDiscoveryStore } from '../stores/discovery'
import { useInventoryStore } from '../stores/inventory'

const open  = defineModel({ type: Boolean, default: false })
const props = defineProps({ defaultCity: { type: String, default: '' } })
const emit  = defineEmits(['done'])

const store     = useDiscoveryStore()
const inventory = useInventoryStore()

const sourceOptions = [
  { label: 'Legistar (Web API)', value: 'legistar' },
  { label: 'Agenda PDF URL',     value: 'pdf' },
  { label: 'Paste agenda text',  value: 'text' },
]

function isoDaysAgo(days) { return new Date(Date.now() - days * 864e5).toISOString().slice(0, 10) }

const phase          = ref('form')
const source         = ref('legistar')
const legistarClient = ref('')
const pdfUrl         = ref('')
const agendaText     = ref('')
const since          = ref(isoDaysAgo(365))   // default 12-month lookback
const until          = ref(isoDaysAgo(0))
const result         = ref({})
const runError       = ref('')
const disabled       = ref(false)

// Human-readable badge for the extractor the backend reports it actually used.
const EXTRACTOR_META = {
  vertex:           { label: 'Extracted via Vertex (Gemini)',                 color: 'success', icon: 'mdi-robot-happy-outline' },
  vertex_partial:   { label: 'Vertex (Gemini) — some items used keyword fallback', color: 'warning', icon: 'mdi-robot-confused-outline' },
  keyword_fallback: { label: 'Vertex unavailable — keyword fallback used',    color: 'warning', icon: 'mdi-alert-outline' },
  keyword:          { label: 'Keyword extractor (no LLM)',                     color: 'grey',    icon: 'mdi-format-letter-matches' },
  preextracted:     { label: 'Pre-extracted items (extractor not run)',       color: 'grey',    icon: 'mdi-import' },
  none:             { label: 'No items to extract',                           color: 'grey',    icon: 'mdi-minus-circle-outline' },
}
const extractorMeta = computed(() =>
  EXTRACTOR_META[result.value.extractor] ||
  { label: result.value.extractor, color: 'grey', icon: 'mdi-help-circle-outline' })

const canRun = computed(() =>
  (source.value === 'legistar' && legistarClient.value.trim()) ||
  (source.value === 'pdf' && pdfUrl.value.trim()) ||
  (source.value === 'text' && agendaText.value.trim()))

async function run() {
  runError.value = ''
  disabled.value = false
  const payload = { city: props.defaultCity || 'City of Lewisville' }
  if (source.value === 'legistar') {
    Object.assign(payload, { legistar_client: legistarClient.value.trim(), since: since.value, until: until.value })
  } else if (source.value === 'pdf') {
    payload.pdf_url = pdfUrl.value.trim()
  } else {
    payload.agenda_text = agendaText.value
  }
  try {
    result.value = await store.runAgenda(payload)
    phase.value = 'done'
    try { await inventory.fetchInventory(props.defaultCity || null) } catch { /* non-fatal */ }
    emit('done', result.value)
  } catch (e) {
    const code = e.response?.status
    disabled.value = code === 503
    runError.value = code === 503
      ? 'The agenda engine is disabled. Set AGENDA_ENGINE_ENABLED=true on the backend to enable it.'
      : code === 403
        ? 'Agenda discovery is restricted to administrators.'
        : (e.response?.data?.detail || e.message)
  }
}

function close() {
  open.value = false
  setTimeout(() => { phase.value = 'form'; result.value = {}; runError.value = '' }, 300)
}
</script>
