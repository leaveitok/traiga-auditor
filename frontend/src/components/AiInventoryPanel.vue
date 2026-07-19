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
        <div class="d-flex ga-2 align-center flex-wrap">
          <v-select v-if="!city && cityOptions.length > 1" v-model="cityFilter"
                    :items="['All cities', ...cityOptions]" density="compact"
                    variant="outlined" hide-details style="min-width: 200px" />
          <!-- AG demand readiness — Tex. Bus. & Com. Code § 552.103(b) -->
          <v-tooltip v-if="city && cidCity" location="bottom" max-width="340"
                     text="Readiness to answer an Attorney General Civil Investigative Demand: the 8 categories of § 552.103(b), per AI system. Gaps are editable on each asset.">
            <template #activator="{ props: tp }">
              <v-chip v-bind="tp" size="small" label variant="tonal"
                      :color="cidCity.city_ready ? 'success' : 'warning'">
                <v-icon start size="14">mdi-file-question-outline</v-icon>
                CID {{ cidCity.ready_count }}/{{ cidCity.asset_count }}
              </v-chip>
            </template>
          </v-tooltip>
          <v-btn v-if="city" color="primary" variant="tonal" size="small"
                 prepend-icon="mdi-file-send-outline"
                 :loading="downloadingPack" @click="downloadPack">
            AG Response Pack
          </v-btn>
          <v-btn v-if="canWrite" color="primary" variant="tonal" size="small"
                 prepend-icon="mdi-plus"
                 @click="openDeclare">Declare AI System</v-btn>
          <!-- Inside-out discovery: merge Sentinel staff-usage telemetry into the registry -->
          <v-tooltip v-if="auth.isPlatformAdmin" location="bottom" max-width="320"
                     text="Pull Sentinel browser-DLP telemetry and add staff AI usage (ChatGPT, Claude, Gemini...) to the registry as discovered assets.">
            <template #activator="{ props: tp }">
              <v-btn v-bind="tp" variant="tonal" color="deep-purple" size="small"
                     prepend-icon="mdi-monitor-eye" :loading="syncing"
                     @click="syncSentinel">Sync Staff Usage</v-btn>
            </template>
          </v-tooltip>
          <!-- Procurement discovery: match an uploaded vendor/spend/contract file -->
          <v-tooltip v-if="auth.canManage" location="bottom" max-width="320"
                     text="Match an uploaded vendor / spend / contract file against the AI tool catalog and add procured AI to the registry.">
            <template #activator="{ props: tp }">
              <v-btn v-bind="tp" variant="tonal" color="teal" size="small"
                     prepend-icon="mdi-file-document-multiple-outline"
                     @click="procurementDialog = true">Import Procurement</v-btn>
            </template>
          </v-tooltip>
          <!-- Council-agenda discovery -->
          <v-tooltip v-if="auth.canManage" location="bottom" max-width="320"
                     text="Scan a city's council/EDC agendas (Legistar, PDF, or pasted text) for awarded AI contracts.">
            <template #activator="{ props: tp }">
              <v-btn v-bind="tp" variant="tonal" color="indigo" size="small"
                     prepend-icon="mdi-gavel"
                     @click="agendaDialog = true">Agendas</v-btn>
            </template>
          </v-tooltip>
          <v-tooltip location="top"
                     text="Import the read-only OAuth export from Microsoft Entra / Google Workspace to find AI apps staff consented to. Dry run by default — writes nothing.">
            <template #activator="{ props: tp }">
              <v-btn v-bind="tp" variant="tonal" color="deep-purple" size="small"
                     prepend-icon="mdi-account-key-outline"
                     @click="oauthDialog = true">OAuth</v-btn>
            </template>
          </v-tooltip>
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
          <v-tooltip v-if="cidFor(item)" location="bottom" max-width="320"
                     :text="cidFor(item).ready
                       ? 'All 8 AG-demand items answerable for this system'
                       : `AG-demand gaps: ${cidFor(item).gaps.join(', ')} — click the pencil to complete`">
            <template #activator="{ props: tp }">
              <v-chip v-bind="tp" size="x-small" label variant="tonal" class="mt-1"
                      :color="cidFor(item).ready ? 'success' : 'warning'">
                CID {{ cidFor(item).answered }}/{{ cidFor(item).total }}
              </v-chip>
            </template>
          </v-tooltip>
        </template>

        <template #item.provenance="{ item }">
          <v-tooltip :text="provenanceTip(item.provenance)">
            <template #activator="{ props }">
              <v-chip v-bind="props" size="small" variant="tonal" label
                      :color="provenanceColor(item.provenance)">
                <v-icon start size="14">{{ provenanceIcon(item.provenance) }}</v-icon>
                {{ provenanceLabel(item.provenance) }}
              </v-chip>
            </template>
          </v-tooltip>
          <v-chip v-if="item.presence === 'not_reobserved'" size="x-small" color="grey"
                  variant="tonal" label class="ml-1">not re-observed</v-chip>
          <div class="mt-1">
            <v-tooltip :text="deploymentMeta(item.provenance).tip">
              <template #activator="{ props }">
                <v-chip v-bind="props" size="x-small" variant="tonal" label
                        :color="deploymentMeta(item.provenance).color">
                  <v-icon start size="12">{{ deploymentMeta(item.provenance).icon }}</v-icon>
                  {{ deploymentMeta(item.provenance).label }}
                </v-chip>
              </template>
            </v-tooltip>
          </div>
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

          <!-- AG demand answers (§ 552.103(b)) — what the AG can ask about this system -->
          <v-expansion-panels class="mt-3" variant="accordion">
            <v-expansion-panel>
              <v-expansion-panel-title class="text-body-2">
                <v-icon start size="18" color="primary">mdi-file-question-outline</v-icon>
                AG demand answers (§ 552.103(b))
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <p class="text-caption text-medium-emphasis mb-2">
                  If the Attorney General investigates, these are the questions the law lets them ask.
                  Vendor-run systems auto-answer the training-data item with a vendor referral —
                  fill it in only if you know more. An honest "none" is a complete answer; a blank is not.
                </p>
                <v-textarea v-model="attestForm.cid_training_data" rows="2" class="mb-1"
                            label="Training data (b2) — leave blank for vendor systems"
                            variant="outlined" density="compact" />
                <v-textarea v-model="attestForm.cid_outputs" rows="2" class="mb-1"
                            label="Outputs (b4) — auto-answered for chatbots; override here"
                            variant="outlined" density="compact" />
                <v-textarea v-model="attestForm.cid_metrics" rows="2" class="mb-1"
                            label="Performance metrics (b5) — e.g. 'none maintained by city; vendor reports monthly'"
                            variant="outlined" density="compact" />
                <v-textarea v-model="attestForm.cid_limitations" rows="2"
                            label="Known limitations (b6) — e.g. languages, topics it must not advise on"
                            variant="outlined" density="compact" />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
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

    <!-- Procurement discovery import -->
    <ProcurementImportDialog v-model="procurementDialog" :default-city="city || ''"
                             @done="onProcurementDone" />
    <AgendaDiscoveryDialog v-model="agendaDialog" :default-city="city || ''"
                           @done="onProcurementDone" />
    <OAuthImportDialog v-model="oauthDialog" :default-city="city || ''"
                       @done="onOAuthDone" />

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3500"
                location="bottom right">{{ snackbar.text }}</v-snackbar>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useInventoryStore } from '../stores/inventory'
import { useAuthStore } from '../stores/auth'
import { useCidStore } from '../stores/cid'
import ProcurementImportDialog from './ProcurementImportDialog.vue'
import AgendaDiscoveryDialog from './AgendaDiscoveryDialog.vue'
import OAuthImportDialog from './OAuthImportDialog.vue'

const props = defineProps({
  /** When set, the panel is locked to one city (CityDetailView embed). */
  city: { type: String, default: null },
})

const store = useInventoryStore()
const auth  = useAuthStore()
const cid   = useCidStore()

// ── CID (AG demand) readiness — city-scoped panels only ─────────────────────
const downloadingPack = ref(false)

// ── Procurement discovery import ────────────────────────────────────────────
const procurementDialog = ref(false)
const agendaDialog = ref(false)
const oauthDialog = ref(false)
function onProcurementDone(res) {
  snackbar.text  = `Procurement: ${res?.matched ?? 0} AI vendor(s) matched, ${res?.written ?? 0} added/updated`
  snackbar.color = 'success'
  snackbar.show  = true
  refresh()
}

/** OAuth discovery finished. A dry run wrote nothing — say so plainly rather than
 *  implying the inventory changed. */
function onOAuthDone(res) {
  snackbar.text = res?.dry_run
    ? `OAuth dry run: ${res?.matched ?? 0} matched, ${res?.candidates ?? 0} to review — nothing written`
    : `OAuth: ${res?.matched ?? 0} AI app(s) matched, ${res?.written ?? 0} added/updated`
  snackbar.color = res?.dry_run ? 'info' : 'success'
  snackbar.show  = true
  if (!res?.dry_run) refresh()
}

const cidCity = computed(() => (props.city ? cid.byCity[props.city] || null : null))

const cidByKey = computed(() => {
  const map = {}
  for (const a of cidCity.value?.assets || []) map[a.asset_key] = a
  return map
})

const cidFor = (item) => cidByKey.value[item.asset_key] || null

async function downloadPack() {
  downloadingPack.value = true
  try {
    await cid.downloadPackage(props.city)
  } catch (e) {
    toast(e.response?.data?.detail || e.message, 'error')
  } finally {
    downloadingPack.value = false
  }
}

// ── Provenance display (WHERE the item was inventoried from) ─────────────────
// Every discovery channel gets a distinct chip. Missing entries here previously
// made agenda/procurement items render as "Declared" — the source is now explicit.
const provenanceLabel = (p) => ({
  discovered_scan: 'Website scan', discovered_agenda: 'Council agenda',
  discovered_procurement: 'Procurement', discovered_budget: 'Budget',
  discovered_sentinel: 'Staff usage', declared: 'Declared',
}[p] || 'Declared')
const provenanceColor = (p) => ({
  discovered_scan: 'indigo', discovered_agenda: 'blue', discovered_procurement: 'cyan',
  discovered_budget: 'light-blue', discovered_sentinel: 'deep-purple', declared: 'teal',
}[p] || 'teal')
const provenanceIcon = (p) => ({
  discovered_scan: 'mdi-radar', discovered_agenda: 'mdi-gavel',
  discovered_procurement: 'mdi-file-document-outline', discovered_budget: 'mdi-cash-multiple',
  discovered_sentinel: 'mdi-monitor-eye', declared: 'mdi-account-edit',
}[p] || 'mdi-account-edit')
const provenanceTip = (p) => ({
  discovered_scan: 'Found automatically by the compliance scanner (public website)',
  discovered_agenda: 'Found in a council/EDC meeting agenda (procurement record)',
  discovered_procurement: 'Found in an uploaded procurement / contract file',
  discovered_budget: 'Found in the adopted budget document',
  discovered_sentinel: 'Observed by Sentinel browser DLP: staff using this AI tool on city devices',
  declared: 'Declared by your team',
}[p] || 'Declared by your team')

// ── Deployment state (IS it live, or only procured/planned?) ────────────────
// Derived from provenance. A website-scan hit is LIVE on the public site — a real
// TRAIGA disclosure obligation now. An agenda/budget/procurement hit is PROCURED or
// PLANNED and may not be deployed yet, so it must NOT read as a live violation:
// surfacing this prevents an implementation-timing gap looking like a false positive.
const _DEPLOYMENT = {
  discovered_scan:        { label: 'Live on site',     color: 'green',       icon: 'mdi-access-point-check',
                            tip: 'Observed on the public website by the scanner — a live disclosure obligation.' },
  discovered_agenda:      { label: 'Procured · verify', color: 'blue',        icon: 'mdi-clipboard-check-outline',
                            tip: 'Found in a procurement record (agenda), not verified live. Confirm it is deployed before treating it as a live disclosure obligation.' },
  discovered_procurement: { label: 'Procured · verify', color: 'blue',        icon: 'mdi-clipboard-check-outline',
                            tip: 'Found in a procurement record, not verified live. Confirm it is deployed before treating it as a live disclosure obligation.' },
  discovered_budget:      { label: 'Budgeted · verify', color: 'blue',        icon: 'mdi-clipboard-check-outline',
                            tip: 'Found in the adopted budget — planned/funded, not verified live. Confirm it is deployed.' },
  discovered_sentinel:    { label: 'Staff-reported',    color: 'deep-purple', icon: 'mdi-monitor-eye',
                            tip: 'Observed in staff browser usage on city devices.' },
  declared:               { label: 'Self-declared',     color: 'teal',        icon: 'mdi-account-check-outline',
                            tip: 'Declared by your team.' },
}
const deploymentMeta = (p) => _DEPLOYMENT[p] || _DEPLOYMENT.declared

// ── Sentinel usage sync (platform admin) ────────────────────────────────────
const syncing = ref(false)

async function syncSentinel() {
  syncing.value = true
  try {
    const r = await store.syncSentinel()
    toast(`Staff usage synced: ${r.synced} assets across ${r.cities.length} `
      + `cit${r.cities.length === 1 ? 'y' : 'ies'}`
      + (r.skipped_untagged_events ? ` (${r.skipped_untagged_events} untagged events skipped)` : ''))
    refresh()
    if (props.city) cid.fetchReadiness(props.city)
  } catch (e) {
    toast(e.response?.data?.detail || e.message, 'error')
  } finally {
    syncing.value = false
  }
}

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
    cid_training_data: item.cid_training_data || '',
    cid_outputs:       item.cid_outputs || '',
    cid_metrics:       item.cid_metrics || '',
    cid_limitations:   item.cid_limitations || '',
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
      cid_training_data: f.cid_training_data,
      cid_outputs:       f.cid_outputs,
      cid_metrics:       f.cid_metrics,
      cid_limitations:   f.cid_limitations,
      // Discovered records get attested on save; already-attested just edit.
      ...(f.lifecycle_status === 'discovered' ? { lifecycle_status: 'attested' } : {}),
    })
    toast(f.lifecycle_status === 'discovered'
      ? `${f.display_name} attested` : `${f.display_name} updated`)
    attestDialog.value = false
    if (props.city) cid.fetchReadiness(props.city)   // re-derive AG readiness
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

onMounted(() => {
  refresh()
  if (props.city) cid.fetchReadiness(props.city)
})
</script>
