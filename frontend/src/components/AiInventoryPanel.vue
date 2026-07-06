<template>
  <div>
    <!-- ── KPI strip: the "needs attestation" count is the to-do list ────── -->
    <v-row dense class="mb-4">
      <v-col cols="6" md="3">
        <v-card variant="tonal" color="primary" class="text-center pa-3">
          <div class="text-h4 font-weight-bold">{{ store.active.length }}</div>
          <div class="text-caption">AI Systems</div>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" :color="store.needsAttestation ? 'warning' : 'success'"
                class="text-center pa-3">
          <div class="text-h4 font-weight-bold">{{ store.needsAttestation }}</div>
          <div class="text-caption">Need Attestation</div>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" color="success" class="text-center pa-3">
          <div class="text-h4 font-weight-bold">{{ store.attested }}</div>
          <div class="text-caption">Attested</div>
        </v-card>
      </v-col>
      <v-col cols="6" md="3">
        <v-card variant="tonal" :color="store.undisclosed ? 'error' : 'success'"
                class="text-center pa-3">
          <div class="text-h4 font-weight-bold">{{ store.undisclosed }}</div>
          <div class="text-caption">Open Violations</div>
        </v-card>
      </v-col>
    </v-row>

    <v-card>
      <v-card-title class="d-flex align-center justify-space-between flex-wrap ga-2">
        <span class="text-subtitle-1 font-weight-bold">
          <v-icon start color="primary">mdi-clipboard-list-outline</v-icon>
          AI Use-Case Inventory
        </span>
        <div class="d-flex ga-2 align-center">
          <v-select v-if="!city && cityOptions.length > 1" v-model="cityFilter"
                    :items="['All cities', ...cityOptions]" density="compact"
                    variant="outlined" hide-details style="min-width: 200px" />
          <v-btn v-if="canWrite" color="primary" prepend-icon="mdi-plus"
                 @click="openDeclare">Declare AI System</v-btn>
          <v-btn icon="mdi-refresh" variant="text" :loading="store.loading" @click="refresh" />
        </div>
      </v-card-title>

      <v-alert v-if="store.error" type="error" density="compact" class="mx-4 mb-2" closable>
        {{ store.error }}
      </v-alert>

      <v-data-table :headers="headers" :items="visibleAssets" :loading="store.loading"
                    item-value="asset_key" show-expand density="comfortable" hover>
        <template #item.display_name="{ item }">
          <div class="font-weight-medium">{{ item.display_name || item.vendor_id || 'Unknown' }}</div>
          <div class="text-caption text-medium-emphasis">
            {{ (item.asset_types || []).map(t => String(t).replace(/_/g, ' ')).join(', ') || 'AI system' }}
          </div>
        </template>

        <template #item.provenance="{ item }">
          <v-tooltip :text="item.provenance === 'discovered_scan'
            ? 'Found automatically by the compliance scanner' : 'Declared by your team'">
            <template #activator="{ props }">
              <v-chip v-bind="props" size="small" variant="tonal" label
                      :color="item.provenance === 'discovered_scan' ? 'indigo' : 'teal'">
                <v-icon start size="14">
                  {{ item.provenance === 'discovered_scan' ? 'mdi-radar' : 'mdi-account-edit' }}
                </v-icon>
                {{ item.provenance === 'discovered_scan' ? 'Discovered' : 'Declared' }}
              </v-chip>
            </template>
          </v-tooltip>
          <v-chip v-if="item.presence === 'not_reobserved'" size="x-small" color="grey"
                  variant="tonal" label class="ml-1">not re-observed</v-chip>
        </template>

        <template #item.disclosure_status="{ item }">
          <v-chip size="small" variant="tonal" label :color="disclosureColor(item)">
            <v-icon start size="14">{{ disclosureIcon(item) }}</v-icon>
            {{ disclosureLabel(item) }}
          </v-chip>
        </template>

        <template #item.owner_email="{ item }">
          <span v-if="item.owner_name || item.owner_email">
            {{ item.owner_name || item.owner_email }}
          </span>
          <v-btn v-else-if="canWrite" size="x-small" variant="text" color="primary"
                 @click="openAttest(item)">Assign owner</v-btn>
          <span v-else class="text-caption text-medium-emphasis">—</span>
        </template>

        <template #item.lifecycle_status="{ item }">
          <v-chip size="small" label variant="tonal" :color="lifecycleColor(item.lifecycle_status)">
            {{ lifecycleLabel(item.lifecycle_status) }}
          </v-chip>
        </template>

        <template #item.actions="{ item }">
          <template v-if="canWrite && item.lifecycle_status !== 'retired'">
            <v-btn v-if="item.lifecycle_status === 'discovered'" size="small" color="primary"
                   variant="tonal" prepend-icon="mdi-check-decagram"
                   @click="openAttest(item)">Confirm &amp; Attest</v-btn>
            <v-btn v-else size="small" variant="text" icon="mdi-pencil" @click="openAttest(item)" />
            <v-btn size="small" variant="text" color="error" icon="mdi-archive-arrow-down"
                   @click="confirmRetire(item)" />
          </template>
        </template>

        <template #expanded-row="{ columns, item }">
          <tr>
            <td :colspan="columns.length" class="pa-4 bg-grey-lighten-5">
              <v-row dense>
                <v-col cols="12" md="6">
                  <div class="text-caption font-weight-bold mb-1">Evidence</div>
                  <div v-if="item.provenance === 'discovered_scan'" class="text-body-2">
                    <div v-if="item.page_url">
                      Observed at <a :href="item.page_url" target="_blank" rel="noopener">{{ item.page_url }}</a>
                    </div>
                    <div v-if="item.match_confidence">
                      Detection confidence: {{ Math.round(Number(item.match_confidence) * 100) }}%
                    </div>
                    <div class="text-caption text-medium-emphasis">
                      First observed {{ shortDate(item.first_observed_utc) }} ·
                      last observed {{ shortDate(item.last_observed_utc) }}
                    </div>
                  </div>
                  <div v-else class="text-body-2">
                    Declared by {{ item.attested_by || 'team' }} {{ shortDate(item.attested_utc) }}
                  </div>
                  <template v-if="item.department || item.purpose">
                    <div class="text-caption font-weight-bold mt-2 mb-1">Context</div>
                    <div class="text-body-2">
                      <span v-if="item.department"><strong>Dept:</strong> {{ item.department }} · </span>
                      <span v-if="item.purpose">{{ item.purpose }}</span>
                    </div>
                  </template>
                  <div v-if="(item.data_categories || []).length" class="mt-1">
                    <v-chip v-for="c in item.data_categories" :key="c" size="x-small"
                            color="deep-orange" variant="tonal" label class="mr-1">{{ c }}</v-chip>
                  </div>
                </v-col>
                <v-col cols="12" md="6">
                  <div class="text-caption font-weight-bold mb-1">Statutory obligations</div>
                  <div v-for="o in item.obligations" :key="o.rule_id" class="text-body-2 mb-1">
                    <v-icon size="14" class="mr-1"
                            :color="o.severity === 'high' ? 'error' : 'warning'">mdi-scale-balance</v-icon>
                    {{ o.title }} <span class="text-caption text-medium-emphasis">({{ o.citation }})</span>
                  </div>
                  <div v-if="item.attested_by && item.lifecycle_status === 'attested'"
                       class="text-caption text-medium-emphasis mt-2">
                    Attested by {{ item.attested_by }} {{ shortDate(item.attested_utc) }}
                    · next review {{ shortDate(item.next_review_utc) }}
                  </div>
                </v-col>
              </v-row>
            </td>
          </tr>
        </template>

        <template #no-data>
          <div class="text-center py-10 text-medium-emphasis">
            <v-icon size="44" class="mb-2">mdi-radar</v-icon>
            <div class="text-body-2">
              No AI systems on record yet. Run an audit — discovered systems
              appear here automatically{{ canWrite ? ', or declare one your team uses' : '' }}.
            </div>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- ── Attest / edit dialog (pre-filled — never a blank form) ─────────── -->
    <v-dialog v-model="attestDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">
          {{ attestForm.lifecycle_status === 'discovered' ? 'Confirm & Attest' : 'Edit Asset' }}
        </v-card-title>
        <v-card-text>
          <v-alert v-if="attestForm.provenance === 'discovered_scan'" type="info"
                   variant="tonal" density="compact" class="mb-3">
            Found by the scanner on <strong>{{ attestForm.city }}</strong>'s website.
            Confirm it, assign an owner, and add context — that's it.
          </v-alert>
          <v-text-field v-model="attestForm.display_name" label="System name"
                        variant="outlined" density="comfortable" class="mb-2" />
          <v-row dense>
            <v-col cols="6">
              <v-text-field v-model="attestForm.owner_name" label="Owner name"
                            variant="outlined" density="comfortable" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="attestForm.owner_email" label="Owner email" type="email"
                            variant="outlined" density="comfortable" />
            </v-col>
          </v-row>
          <v-text-field v-model="attestForm.department" label="Department"
                        variant="outlined" density="comfortable" class="mb-2"
                        placeholder="e.g. 311 / Customer Service" />
          <v-textarea v-model="attestForm.purpose" label="Purpose" rows="2"
                      variant="outlined" density="comfortable" class="mb-2"
                      placeholder="What does this system do for residents or staff?" />
          <v-select v-model="attestForm.data_categories" :items="DATA_CATEGORIES"
                    label="Data it may touch" multiple chips closable-chips
                    variant="outlined" density="comfortable"
                    hint="Used for risk weighting — pick all that apply" persistent-hint />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="attestDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveAttest">
            {{ attestForm.lifecycle_status === 'discovered' ? 'Attest' : 'Save' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Declare dialog (for what scans can't see) ──────────────────────── -->
    <v-dialog v-model="declareDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">Declare AI System</v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-3">
            For AI your team uses that a website scan can't see — internal
            tools, vendor systems, decision-support software.
          </p>
          <v-select v-if="!city" v-model="declareForm.city" :items="cityOptions"
                    label="City" variant="outlined" density="comfortable" class="mb-2" />
          <v-text-field v-model="declareForm.display_name" label="System name"
                        variant="outlined" density="comfortable" class="mb-2"
                        placeholder="e.g. ChatGPT Enterprise, RFP scoring tool" />
          <v-select v-model="declareForm.asset_types" :items="ASSET_TYPES"
                    label="Type" multiple chips variant="outlined" density="comfortable" class="mb-2" />
          <v-text-field v-model="declareForm.department" label="Department"
                        variant="outlined" density="comfortable" class="mb-2" />
          <v-textarea v-model="declareForm.purpose" label="Purpose" rows="2"
                      variant="outlined" density="comfortable" class="mb-2" />
          <v-select v-model="declareForm.data_categories" :items="DATA_CATEGORIES"
                    label="Data it may touch" multiple chips closable-chips
                    variant="outlined" density="comfortable" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="declareDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving"
                 :disabled="!declareForm.display_name || !(city || declareForm.city)"
                 @click="saveDeclare">Declare</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Retire confirm ─────────────────────────────────────────────────── -->
    <v-dialog v-model="retireDialog" max-width="440">
      <v-card>
        <v-card-title class="text-h6">Retire asset?</v-card-title>
        <v-card-text>
          Mark <strong>{{ retireTarget?.display_name || retireTarget?.vendor_id }}</strong> as
          retired? The record is kept for audit history — nothing is deleted.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="retireDialog = false">Cancel</v-btn>
          <v-btn color="error" :loading="saving" @click="doRetire">Retire</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3500"
                location="bottom right">{{ snackbar.text }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useInventoryStore } from '../stores/inventory'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  /** When set, the panel is locked to one city (CityDetailView embed). */
  city: { type: String, default: null },
})

const store = useInventoryStore()
const auth  = useAuthStore()

const cityFilter    = ref('All cities')
const saving        = ref(false)
const snackbar      = reactive({ show: false, text: '', color: 'success' })
const attestDialog  = ref(false)
const declareDialog = ref(false)
const retireDialog  = ref(false)
const retireTarget  = ref(null)
const attestForm    = ref({})
const declareForm   = ref({})

const DATA_CATEGORIES = ['PII', 'CJIS', 'HIPAA', 'Financial', 'Public only']
const ASSET_TYPES = [
  'chatbot', 'automated_intake_widget', 'decision_widget',
  'genai_tool', 'document_processing', 'biometric', 'other',
]

// Write access mirrors the server rule: platform admin, or agency admin.
const canWrite = computed(() => auth.isPlatformAdmin || auth.isAgencyAdmin)

const cityOptions = computed(() =>
  [...new Set(store.assets.map(a => a.city))].sort())

const visibleAssets = computed(() => {
  let rows = store.assets
  if (props.city) rows = rows.filter(a => a.city === props.city)
  else if (cityFilter.value && cityFilter.value !== 'All cities')
    rows = rows.filter(a => a.city === cityFilter.value)
  // Workflow ordering: needs-attestation first, then attested, retired last.
  const rank = { discovered: 0, attested: 1, retired: 2 }
  return [...rows].sort((a, b) =>
    (rank[a.lifecycle_status] ?? 1) - (rank[b.lifecycle_status] ?? 1))
})

const headers = computed(() => [
  { title: 'AI System', key: 'display_name' },
  ...(props.city ? [] : [{ title: 'City', key: 'city' }]),
  { title: 'Source', key: 'provenance', sortable: false },
  { title: 'Disclosure', key: 'disclosure_status', sortable: false },
  { title: 'Owner', key: 'owner_email', sortable: false },
  { title: 'Status', key: 'lifecycle_status' },
  { title: '', key: 'actions', sortable: false, align: 'end' },
])

const disclosureColor = (a) => a.lifecycle_status === 'retired' ? 'grey'
  : ({ non_compliant: 'error', compliant: 'success', not_assessed: 'blue-grey' }[a.disclosure_status] || 'blue-grey')
const disclosureIcon = (a) =>
  ({ non_compliant: 'mdi-alert-circle', compliant: 'mdi-check-circle' }[a.disclosure_status] || 'mdi-help-circle')
const disclosureLabel = (a) => ({
  non_compliant: `${a.open_violation_count} open violation${Number(a.open_violation_count) > 1 ? 's' : ''}`,
  compliant: 'Compliant', not_assessed: 'Not assessed',
}[a.disclosure_status] || a.disclosure_status)

const lifecycleColor = (s) => ({ discovered: 'warning', attested: 'success', retired: 'grey' }[s] || 'default')
const lifecycleLabel = (s) => ({ discovered: 'Needs attestation', attested: 'Attested', retired: 'Retired' }[s] || s)

const shortDate = (iso) => {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString() } catch { return iso }
}

function refresh() { store.fetchInventory(props.city) }

function openAttest(item) {
  attestForm.value = {
    asset_key:        item.asset_key,
    provenance:       item.provenance,
    lifecycle_status: item.lifecycle_status,
    city:             item.city,
    display_name:     item.display_name || item.vendor_id,
    owner_name:       item.owner_name || '',
    owner_email:      item.owner_email || '',
    department:       item.department || '',
    purpose:          item.purpose || '',
    data_categories:  [...(item.data_categories || [])],
  }
  attestDialog.value = true
}

async function saveAttest() {
  saving.value = true
  try {
    const f = attestForm.value
    await store.update(f.asset_key, {
      display_name:     f.display_name,
      owner_name:       f.owner_name,
      owner_email:      f.owner_email,
      department:       f.department,
      purpose:          f.purpose,
      data_categories:  f.data_categories,
      // Discovered records get attested on save; already-attested just edit.
      ...(f.lifecycle_status === 'discovered' ? { lifecycle_status: 'attested' } : {}),
    })
    toast(f.lifecycle_status === 'discovered'
      ? `${f.display_name} attested` : `${f.display_name} updated`)
    attestDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

function openDeclare() {
  declareForm.value = {
    city: props.city || null, display_name: '', asset_types: [],
    department: '', purpose: '', data_categories: [],
  }
  declareDialog.value = true
}

async function saveDeclare() {
  saving.value = true
  try {
    const f = declareForm.value
    await store.declare({
      city:            props.city || f.city,
      display_name:    f.display_name,
      asset_types:     f.asset_types,
      department:      f.department || null,
      purpose:         f.purpose || null,
      data_categories: f.data_categories,
    })
    toast(`${f.display_name} added to inventory`)
    declareDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

function confirmRetire(item) { retireTarget.value = item; retireDialog.value = true }
async function doRetire() {
  saving.value = true
  try {
    await store.update(retireTarget.value.asset_key, { lifecycle_status: 'retired' })
    toast(`${retireTarget.value.display_name || 'Asset'} retired`)
    retireDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

function toast(text, color = 'success') {
  snackbar.text = text; snackbar.color = color; snackbar.show = true
}

onMounted(refresh)
</script>
