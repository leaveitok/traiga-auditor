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
        {{ effectiveCity ? `Re-Audit ${effectiveCity}` : (auth.isAdmin ? 'Run Audit' : `Audit ${auth.city || 'My City'}`) }}
      </v-btn>

      <v-chip v-if="auditStore.status !== 'idle' && !auditStore.isRunning"
              :color="statusColor"
              :prepend-icon="statusIcon"
              label>
        {{ statusLabel }}
      </v-chip>
    </div>

    <!-- Progress bar shown only while running -->
    <div v-if="auditStore.isRunning" style="width: 100%; max-width: 420px">
      <v-progress-linear
        indeterminate
        color="primary"
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
          {{ effectiveCity ? `Re-Audit ${effectiveCity}` : (auth.isAdmin ? 'Run Audit' : `Audit ${auth.city || 'My City'}`) }}
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
              <v-radio label="Live — crawl all active targets" :value="false" />
              <v-radio label="Demo — offline fixtures (no network)" :value="true" />
            </v-radio-group>
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

const props = defineProps({
  /** When set, locks the audit to this specific city (admin drilling into a city page). */
  cityOverride: { type: String, default: null },
})

const emit = defineEmits(['audit-complete'])

const auditStore = useAuditStore()
const auth       = useAuthStore()
const dialog     = ref(false)
const demoMode   = ref(false)

// The city that will be scanned: prop override > city-scoped user > null (all cities)
const effectiveCity = computed(() =>
  props.cityOverride || (!auth.isAdmin ? auth.city : null)
)

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
const progressMessage = computed(() => PROGRESS_MESSAGES[msgIndex.value])
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

async function startAudit() {
  dialog.value = false
  await auditStore.trigger(demoMode.value, effectiveCity.value)
  emit('audit-complete')
}
</script>
