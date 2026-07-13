<template>
  <div class="d-flex flex-column ga-2" style="min-width: 220px">
    <div class="d-flex align-center ga-3">
      <v-btn
        color="primary"
        prepend-icon="mdi-play-circle"
        :loading="auditStore.isRunning"
        :disabled="auditStore.isRunning"
        @click="dialog = true"
      >
        {{ buttonLabel }}
      </v-btn>

      <v-chip v-if="auditStore.status !== 'idle' && !auditStore.isRunning"
              :color="statusColor"
              :prepend-icon="statusIcon"
              label>
        {{ statusLabel }}
      </v-chip>

      <!-- Live residential-proxy indicator: the paid path is amber (= cost). -->
      <v-chip v-if="auditStore.isRunning && proxyActive"
              color="amber-darken-2" variant="flat" label size="small"
              prepend-icon="mdi-shield-globe">
        Residential IP
      </v-chip>
    </div>

    <!-- Progress bar shown only while running -->
    <div v-if="auditStore.isRunning" style="width: 100%; max-width: 420px">
      <v-progress-linear
        :indeterminate="!auditStore.progress || !auditStore.progress.total"
        :model-value="auditStore.progress && auditStore.progress.total
          ? (auditStore.progress.completed / auditStore.progress.total) * 100
          : 0"
        :color="proxyActive ? 'amber-darken-2' : 'primary'"
        rounded
        height="6"
        class="mb-1"
      />
      <div class="d-flex align-center ga-1 text-caption text-medium-emphasis">
        <v-icon size="12" class="mdi-spin">mdi-loading</v-icon>
        {{ progressMessage }}
      </div>
    </div>

    <!-- Confirm dialog -->
    <v-dialog v-model="dialog" max-width="480">
      <v-card>
        <v-card-title class="text-h6">
          {{ buttonLabel }}
        </v-card-title>
        <v-card-text>
          <!-- City locked (city-scoped user OR admin drilling into a city page) -->
          <v-alert v-if="effectiveCity" type="info" variant="tonal" density="compact" class="mb-3">
            Only <strong>{{ effectiveCity }}</strong> will be scanned.
          </v-alert>

          <!-- Admin run mode (shown when not locked to a specific city) -->
          <template v-if="auth.isAdmin && !effectiveCity">
            <p class="mb-3">Choose run mode:</p>
            <v-radio-group v-model="demoMode" inline>
              <v-radio label="Live — crawl selected targets" :value="false" />
              <v-radio label="Demo — offline fixtures (no network)" :value="true" />
            </v-radio-group>
            <v-select
              v-if="!demoMode"
              v-model="selectedCities"
              :items="cityOptions"
              label="Cities to audit"
              multiple chips closable-chips clearable
              variant="outlined" density="comfortable"
              prepend-inner-icon="mdi-city"
              hint="Leave empty to audit all your cities" persistent-hint
            />
          </template>
          <template v-else-if="auth.isAdmin && effectiveCity">
            <v-radio-group v-model="demoMode" inline>
              <v-radio label="Live crawl" :value="false" />
              <v-radio label="Demo (offline fixtures)" :value="true" />
            </v-radio-group>
          </template>
          <template v-else>
            <p class="text-body-2 text-medium-emphasis">
              This will crawl <strong>{{ effectiveCity }}</strong> and check for
              TRAIGA disclosure compliance.
            </p>
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">Cancel</v-btn>
          <v-btn color="primary" @click="startAudit">Start</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useAuditStore } from '../stores/audit'
import { useAuthStore }  from '../stores/auth'
import { useScorecardStore } from '../stores/scorecard'

const props = defineProps({
  /** When set, locks the audit to this specific city (admin drilling into a city page). */
  cityOverride: { type: String, default: null },
  /** True when this city has never been assessed — the button reads "Audit", not "Re-Audit". */
  neverScanned: { type: Boolean, default: false },
})

const emit = defineEmits(['audit-complete'])

const auditStore = useAuditStore()
const auth       = useAuthStore()
const scorecard  = useScorecardStore()
const dialog     = ref(false)
const demoMode   = ref(false)
const selectedCities = ref([])

// Cities the caller may audit: platform admin -> all scorecard cities;
// scoped users -> their granted cities.
const cityOptions = computed(() => {
  if (auth.isPlatformAdmin) {
    return [...new Set(scorecard.rows.map(r => r.city))].sort()
  }
  return [...(auth.cities || [])].sort()
})

// The city that will be scanned: prop override > city-scoped user > null (all cities)
const effectiveCity = computed(() =>
  props.cityOverride || (!auth.isAdmin ? auth.city : null)
)

// "Audit" on a city's first run, "Re-Audit" thereafter.
const buttonLabel = computed(() => {
  if (effectiveCity.value) {
    return `${props.neverScanned ? 'Audit' : 'Re-Audit'} ${effectiveCity.value}`
  }
  return auth.isAdmin ? 'Run Audit' : `Audit ${auth.city || 'My City'}`
})

// Rotating progress messages — no fabricated time estimates
const PROGRESS_MESSAGES = [
  'Connecting to audit targets…',
  'Crawling city domains…',
  'Scanning for AI disclosure signals…',
  'Checking TRAIGA §552.051 requirements…',
  'Analyzing biometric disclosure compliance…',
  'Evaluating chatbot and AI asset disclosures…',
  'Computing compliance scores…',
  'Writing violations to audit log…',
  'Finalizing results…',
]

const msgIndex       = ref(0)
// Real per-city progress from the backend when available; rotating
// messages only as a fallback before the first progress packet arrives.
const progressMessage = computed(() => {
  const p = auditStore.progress
  if (p && p.total) {
    const n = Math.min(p.completed + 1, p.total)
    return p.current_city
      ? `Scanning ${p.current_city} (${n} of ${p.total})…`
      : `Scanning ${n} of ${p.total}…`
  }
  return PROGRESS_MESSAGES[msgIndex.value]
})
let   _msgTimer      = null

watch(() => auditStore.isRunning, (running) => {
  if (running) {
    msgIndex.value = 0
    _msgTimer = setInterval(() => {
      // Advance through messages but hold on the last one
      if (msgIndex.value < PROGRESS_MESSAGES.length - 1) msgIndex.value++
    }, 8000)
  } else {
    clearInterval(_msgTimer)
    _msgTimer = null
  }
})

onUnmounted(() => clearInterval(_msgTimer))

// True while the current city is being crawled through the residential proxy
// (the paid path). Surfaced live so the operator always knows when it's in use.
const proxyActive = computed(() => !!auditStore.progress?.proxy_active)

const statusColor = computed(() => ({
  running:   'info',
  completed: 'success',
  error:     'error',
  idle:      'default',
}[auditStore.status] || 'default'))

const statusIcon = computed(() => ({
  running:   'mdi-loading mdi-spin',
  completed: 'mdi-check-circle',
  error:     'mdi-alert',
  idle:      'mdi-clock-outline',
}[auditStore.status] || 'mdi-clock-outline'))

const statusLabel = computed(() => ({
  running:   'Running…',
  completed: `Done — ${auditStore.cityCount} cities, ${auditStore.openViolations} open violations`,
  error:     `Error: ${auditStore.errorMsg}`,
  idle:      'Idle',
}[auditStore.status] || auditStore.status))

// Emit audit-complete when the scan actually FINISHES (status transition),
// not when the trigger POST returns — the scan runs as a background task.
watch(() => auditStore.status, (s, prev) => {
  if (prev === 'running' && s === 'completed') emit('audit-complete')
})

async function startAudit() {
  dialog.value = false
  const cities = (!effectiveCity.value && selectedCities.value.length)
    ? selectedCities.value : null
  await auditStore.trigger(demoMode.value, effectiveCity.value, cities)
  selectedCities.value = []
}
</script>
