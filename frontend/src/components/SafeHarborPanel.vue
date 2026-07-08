<template>
  <v-card class="mt-6">
    <v-card-title class="d-flex align-center flex-wrap ga-2">
      <v-icon class="mr-1" color="primary">mdi-gavel</v-icon>
      TRAIGA Safe Harbor Readiness
      <v-chip v-if="readiness" size="small" label variant="flat"
              :color="bandColor(readiness.band)">
        {{ bandLabel(readiness.band) }} — {{ readiness.overall.satisfied }}/{{ readiness.overall.total }}
      </v-chip>
      <v-spacer />
      <v-btn
        v-if="readiness"
        color="primary" variant="tonal" size="small"
        prepend-icon="mdi-file-certificate-outline"
        :loading="downloading"
        @click="downloadStatement"
      >
        Alignment Statement
      </v-btn>
    </v-card-title>

    <v-card-subtitle class="text-wrap">
      {{ readiness?.profile_name || 'Municipal AI Profile' }}
      v{{ readiness?.profile_version || '1.0' }} — NIST AI RMF + Generative AI Profile.
      Supports the reasonable-care presumption and internal-review defenses under
      Tex. Bus. &amp; Com. Code § 552.105(c)–(e).
    </v-card-subtitle>

    <v-card-text>
      <v-alert v-if="store.error" type="error" variant="tonal" density="compact" class="mb-3">
        {{ store.error }}
      </v-alert>

      <div v-if="store.loading && !readiness" class="text-center py-6">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-else-if="readiness">
        <!-- Function rings -->
        <v-row class="mb-2" justify="center">
          <v-col v-for="fn in functions" :key="fn" cols="6" sm="3" class="text-center">
            <v-progress-circular
              :model-value="(readiness.scores[fn]?.pct || 0) * 100"
              :size="72" :width="7"
              :color="ringColor(readiness.scores[fn]?.pct || 0)"
            >
              {{ readiness.scores[fn]?.satisfied || 0 }}/{{ readiness.scores[fn]?.total || 0 }}
            </v-progress-circular>
            <div class="text-caption font-weight-medium mt-1">{{ fn.toUpperCase() }}</div>
          </v-col>
        </v-row>

        <!-- Checklist grouped by function -->
        <v-expansion-panels variant="accordion" multiple>
          <v-expansion-panel v-for="fn in functions" :key="fn">
            <v-expansion-panel-title>
              <span class="font-weight-medium">{{ fn.toUpperCase() }}</span>
              <v-spacer />
              <span class="text-caption text-medium-emphasis mr-3">
                {{ readiness.scores[fn]?.satisfied || 0 }} of {{ readiness.scores[fn]?.total || 0 }} satisfied
              </span>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div v-for="c in controlsFor(fn)" :key="c.control_id"
                   class="d-flex align-start ga-3 py-2 border-b">
                <v-icon :color="statusColor(c.status)" size="small" class="mt-1">
                  {{ statusIcon(c.status) }}
                </v-icon>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">
                    {{ c.title }}
                    <span class="text-caption text-medium-emphasis">· {{ c.nist_ref }}</span>
                  </div>
                  <div class="text-caption text-medium-emphasis">{{ c.plain }}</div>
                  <div v-if="c.attestation?.status === 'attested'" class="text-caption mt-1">
                    <v-icon size="x-small">mdi-account-check-outline</v-icon>
                    Attested by {{ c.attestation.attested_by }}
                    {{ fmtDate(c.attestation.attested_utc) }}
                    <span v-if="c.attestation.notes"> — “{{ c.attestation.notes }}”</span>
                  </div>
                  <div v-else-if="c.basis === 'machine' && c.status === 'satisfied'"
                       class="text-caption text-success mt-1">
                    <v-icon size="x-small">mdi-robot-outline</v-icon>
                    Machine-verified from platform data
                  </div>
                </div>
                <template v-if="canAttest && c.status !== 'satisfied'">
                  <v-btn size="x-small" color="primary" variant="tonal"
                         @click="openAttest(c)">Attest</v-btn>
                </template>
                <template v-else-if="canAttest && c.basis === 'attested'">
                  <v-btn size="x-small" variant="text" color="grey"
                         title="Clear attestation"
                         @click="clearAttest(c)">Clear</v-btn>
                </template>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </template>
    </v-card-text>

    <!-- Attest dialog -->
    <v-dialog v-model="attestDialog" max-width="480">
      <v-card v-if="attesting">
        <v-card-title class="text-subtitle-1">Attest — {{ attesting.title }}</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-2">{{ attesting.plain }}</p>
          <p v-if="attesting.attest_hint" class="text-caption text-medium-emphasis mb-3">
            <v-icon size="x-small">mdi-lightbulb-outline</v-icon> {{ attesting.attest_hint }}
          </p>
          <v-textarea v-model="attestNotes" label="Evidence notes (included in the Alignment Statement)"
                      rows="3" variant="outlined" density="compact" counter="2000" />
          <v-alert type="info" variant="tonal" density="compact" class="mt-1">
            Your name and timestamp are recorded and appear in generated legal documentation.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="attestDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveAttest">Attest</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<script setup>
/**
 * SafeHarborPanel — per-city TRAIGA safe-harbor readiness (Municipal AI Profile).
 * Machine controls derive from scan/inventory/violation data; human controls
 * are attested here. The Alignment Statement docx is the § 552.105 evidence
 * artifact (counsel review required — the document says so itself).
 */
import { ref, computed, onMounted } from 'vue'
import { useSafeHarborStore } from '../stores/safeharbor'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  city: { type: String, required: true },
})

const store = useSafeHarborStore()
const auth  = useAuthStore()

const functions    = ['govern', 'map', 'measure', 'manage']
const attestDialog = ref(false)
const attesting    = ref(null)
const attestNotes  = ref('')
const saving       = ref(false)
const downloading  = ref(false)

const readiness = computed(() => store.byCity[props.city] || null)
const canAttest = computed(() => auth.isPlatformAdmin || auth.isAgencyAdmin)

const controlsFor = (fn) =>
  (readiness.value?.controls || []).filter(c => c.function === fn)

const bandColor  = (b) => ({ ready: 'success', partial: 'warning', early: 'error' }[b] || 'default')
const bandLabel  = (b) => ({ ready: 'Ready', partial: 'Partial', early: 'Early' }[b] || b)
const ringColor  = (pct) => (pct >= 0.85 ? 'success' : pct >= 0.5 ? 'warning' : 'error')
const statusColor = (s) => ({ satisfied: 'success', failing: 'error', open: 'grey' }[s] || 'grey')
const statusIcon  = (s) => ({
  satisfied: 'mdi-check-circle',
  failing: 'mdi-alert-circle',
  open: 'mdi-checkbox-blank-circle-outline',
}[s] || 'mdi-help-circle-outline')

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString() : '')

function openAttest(control) {
  attesting.value = control
  attestNotes.value = control.attestation?.notes || ''
  attestDialog.value = true
}

async function saveAttest() {
  saving.value = true
  try {
    await store.attest(props.city, attesting.value.control_id, 'attested', attestNotes.value)
    attestDialog.value = false
  } finally {
    saving.value = false
  }
}

async function clearAttest(control) {
  await store.attest(props.city, control.control_id, 'open', '')
}

async function downloadStatement() {
  downloading.value = true
  try {
    await store.downloadStatement(props.city)
  } finally {
    downloading.value = false
  }
}

onMounted(() => store.fetchReadiness(props.city))
</script>

<style scoped>
.border-b { border-bottom: 1px solid rgba(128, 128, 128, 0.15); }
</style>
