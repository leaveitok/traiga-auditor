<template>
  <v-dialog v-model="open" max-width="880" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center flex-wrap ga-2">
        <v-icon class="mr-1">mdi-account-key-outline</v-icon>
        Discover Shadow AI (OAuth)
        <v-spacer />
        <v-chip size="small" color="indigo" variant="tonal" prepend-icon="mdi-shield-account">Admin</v-chip>
      </v-card-title>

      <v-card-text>
        <!-- STEP 1 — choose the export file -->
        <template v-if="phase === 'select'">
          <!-- Two supported paths. Method B exists because many municipal shops run
               endpoint protection / AppLocker / WDAC that blocks PowerShell outright.
               We deliberately do NOT ship a .bat that bypasses execution policy: that is
               the behaviour security teams block malware for, and asking a city to weaken
               a control in order to run a compliance tool is the wrong trade. -->
          <v-tabs v-model="method" density="compact" class="mb-3">
            <v-tab value="script">
              <v-icon size="small" class="mr-1">mdi-powershell</v-icon>Run the script
            </v-tab>
            <v-tab value="graph">
              <v-icon size="small" class="mr-1">mdi-web</v-icon>Browser only
            </v-tab>
          </v-tabs>

          <v-alert v-if="method === 'graph'" type="info" variant="tonal" density="compact"
                   class="mb-3">
            Nothing installs and nothing runs on your machine. Use this if endpoint
            protection, AppLocker or WDAC blocks PowerShell — that is a normal control and
            we will not ask you to weaken it.
          </v-alert>

          <!-- ── METHOD A ─────────────────────────────────────────────────── -->
          <template v-if="method === 'script'">
            <div class="mb-3 pa-3 rounded" style="border: 1px solid rgba(128,128,128,0.3)">
              <div class="d-flex align-center flex-wrap ga-2 mb-1">
                <strong>1. Check your role</strong>
              </div>
              <p class="text-caption text-medium-emphasis mb-3">
                You need <strong>Global Reader</strong> (or any role that can read
                applications and directory objects). Read-only is sufficient — you never
                need Global Administrator for this.
              </p>

              <div class="d-flex align-center flex-wrap ga-2 mb-1">
                <strong>2. Install Microsoft's module</strong>
              </div>
              <CopyLine :text="cmd.install" />

              <div class="d-flex align-center flex-wrap ga-2 mb-1 mt-3">
                <strong>3. Download the script</strong>
                <v-spacer />
                <v-btn size="small" color="primary" variant="tonal"
                       prepend-icon="mdi-download" :href="scriptUrl" download>
                  Download script
                </v-btn>
              </div>
              <div v-if="scriptMeta" class="text-caption">
                <code>{{ scriptMeta.filename }}</code>
                <span class="text-medium-emphasis">
                  · release {{ scriptMeta.release }}</span>
                <div class="d-flex align-center flex-wrap ga-1 mt-1">
                  <span class="text-medium-emphasis">SHA-256:</span>
                  <code style="word-break: break-all">{{ scriptMeta.sha256 }}</code>
                  <v-btn size="x-small" variant="text" icon="mdi-content-copy"
                         @click="copy(scriptMeta.sha256)" />
                </div>
                <CopyLine :text="cmd.hash" class="mt-1" />
              </div>

              <v-alert type="warning" variant="tonal" density="compact" class="mt-3 mb-1">
                <strong>4. Unblock it — this step is skipped most often.</strong>
                Windows marks anything downloaded from a browser and PowerShell refuses to
                run marked scripts. Without this you get an execution-policy error.
              </v-alert>
              <CopyLine :text="cmd.unblock" />
              <p class="text-caption text-medium-emphasis mt-1 mb-1">
                Still blocked? This affects only the current window and reverts when you
                close it:
              </p>
              <CopyLine :text="cmd.policy" />
              <p class="text-caption text-medium-emphasis mt-1">
                If your policy forbids either command, switch to <strong>Browser only</strong>
                above. Do not disable a control to run our tool.
              </p>

              <div class="d-flex align-center flex-wrap ga-2 mb-1 mt-3">
                <strong>5. Run it, then read the file it writes</strong>
              </div>
              <CopyLine :text="cmd.run" />
              <p class="text-caption text-medium-emphasis mt-1">
                Sign in as yourself and approve the read permissions. Open the JSON it
                produces and read it before uploading — it contains only what you see there.
              </p>
            </div>

            <div class="d-flex align-center ga-2 mb-1">
              <strong>6. Upload the file it produced</strong>
            </div>
            <v-file-input
              v-model="file"
              label="Select the exported .json file"
              accept=".json,application/json"
              prepend-icon="mdi-code-json"
              density="comfortable"
              :error-messages="parseError"
              @update:model-value="onFile"
            />
          </template>

          <!-- ── METHOD B ─────────────────────────────────────────────────── -->
          <template v-else>
            <div class="mb-3 pa-3 rounded" style="border: 1px solid rgba(128,128,128,0.3)">
              <div class="mb-1"><strong>1. Open Microsoft Graph Explorer</strong></div>
              <p class="text-caption text-medium-emphasis mb-2">
                Microsoft's own tool, not ours. Sign in with your admin account.
              </p>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-open-in-new"
                     href="https://developer.microsoft.com/graph/graph-explorer"
                     target="_blank" rel="noopener">Open Graph Explorer</v-btn>

              <div class="mt-3 mb-1"><strong>2. Run this query, then save the result</strong></div>
              <CopyLine :text="cmd.q1" />
              <p class="text-caption text-medium-emphasis mt-1">
                Leave the method as <strong>GET</strong>. Use the download control on the
                response panel. Save as <code>servicePrincipals.json</code>.
              </p>

              <div class="mt-3 mb-1"><strong>3. Run this one and save it too</strong></div>
              <CopyLine :text="cmd.q2" />
              <p class="text-caption text-medium-emphasis mt-1">
                Save as <code>oauth2PermissionGrants.json</code>.
              </p>

              <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
                <strong>If the response contains <code>@odata.nextLink</code></strong>, your
                tenant has more results than one page and the file you saved is incomplete.
                An incomplete file makes a tenant look cleaner than it is. Run the
                <code>nextLink</code> URL as the next query, save that page too, and repeat
                until no <code>nextLink</code> appears. Upload every page.
              </v-alert>
            </div>

            <div class="d-flex align-center ga-2 mb-1">
              <strong>4. Upload both files</strong>
            </div>
            <v-file-input
              v-model="graphFiles"
              label="Select both downloaded .json files"
              accept=".json,application/json"
              prepend-icon="mdi-code-json"
              density="comfortable"
              multiple
              :error-messages="parseError"
              @update:model-value="onGraphFiles"
            />
            <p class="text-caption text-medium-emphasis">
              Order does not matter — each file is identified by its contents. They are
              joined on our server, exactly as the script would have done locally.
            </p>
          </template>

          <v-switch
            v-model="dryRun"
            color="primary"
            density="compact"
            hide-details
            class="mt-2"
            :label="dryRun
              ? 'Dry run — report findings only, write NOTHING'
              : 'Write results to the AI Inventory'"
          />
          <p class="text-caption text-medium-emphasis mt-1">
            Leave dry run on for a first look. You will see exactly what would be recorded
            before anything is saved.
          </p>

          <v-alert v-if="fileHasUsers" type="warning" variant="tonal" density="compact" class="mt-3">
            This file was exported with <code>-IncludeUsers</code>, so it contains employee
            identities. They are <strong>not</strong> uploaded — only the number of users per
            app is sent. Recording identities requires a platform administrator.
          </v-alert>
        </template>

        <!-- STEP 2 — preview what will be sent -->
        <template v-else-if="phase === 'preview'">
          <v-alert type="info" variant="tonal" density="compact" class="mb-3">
            <template v-if="method === 'script'">
              <strong>{{ grants.length }}</strong> application(s) found in the file for
              <strong>{{ cityName }}</strong>.
            </template>
            <template v-else>
              <strong>{{ graphBlobs.length }}</strong> Graph Explorer file(s) ready for
              <strong>{{ cityName }}</strong>. They will be identified and joined on the
              server.
            </template>
            {{ dryRun ? 'Dry run: nothing will be written.' : 'Results WILL be written to the inventory.' }}
          </v-alert>

          <v-table v-if="method === 'script'" density="compact" class="mb-2">
            <thead>
              <tr>
                <th class="text-left">Application</th>
                <th class="text-left">Publisher</th>
                <th class="text-left">Users</th>
                <th class="text-left">Scopes granted</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(g, i) in grants.slice(0, 25)" :key="i">
                <td class="text-body-2">{{ g.app_name || '—' }}</td>
                <td class="text-caption text-medium-emphasis">{{ g.publisher || '—' }}</td>
                <td class="text-caption">{{ g.user_count ?? '—' }}</td>
                <td class="text-caption text-medium-emphasis">{{ (g.scopes || []).join(', ') || '—' }}</td>
              </tr>
            </tbody>
          </v-table>
          <p v-if="method === 'script' && grants.length > 25" class="text-caption text-medium-emphasis">
            Showing the first 25 of {{ grants.length }}.
          </p>

          <v-alert v-if="runError" type="error" variant="tonal" density="compact" class="mt-3">
            {{ runError }}
          </v-alert>
        </template>

        <!-- STEP 3 — result -->
        <template v-else>
          <v-alert :type="result.dry_run ? 'info' : 'success'" variant="tonal" class="mb-2">
            <template v-if="result.dry_run">
              <strong>Dry run — nothing was written.</strong>
              Matched <strong>{{ result.matched }}</strong>,
              <strong>{{ result.candidates || 0 }}</strong> flagged for review
              from {{ result.rows }} application(s).
            </template>
            <template v-else>
              Matched <strong>{{ result.matched }}</strong>,
              <strong>{{ result.candidates || 0 }}</strong> flagged for review,
              <strong>{{ result.written }}</strong> added/updated
              from {{ result.rows }} application(s).
            </template>
          </v-alert>

          <v-alert v-if="result.dry_run" type="warning" variant="tonal" density="compact" class="mb-2">
            Nothing has been saved yet. Re-run with dry run switched off to record these.
          </v-alert>

          <!-- Completeness problems the SERVER detected (e.g. a paged Graph download).
               A partial export makes a tenant look clean, so this is never swallowed. -->
          <v-alert v-for="(w, i) in (result.source_warnings || [])" :key="i"
                   type="warning" variant="tonal" density="compact" class="mb-2">
            {{ w }}
          </v-alert>

          <p class="text-body-2 mt-3 text-medium-emphasis">
            Recorded items appear as <strong>Procured · verify</strong> — found in a consent
            record, not observed running on your website. Confirm whether each is deployed.
          </p>

          <!-- The signature backlog. This is the most valuable output of a PARTNER run:
               every row is an app we could not identify, with what we need to add it to
               the catalog so every city detects it from then on. -->
          <template v-if="unmatched.length">
            <v-divider class="my-4" />
            <div class="d-flex align-center flex-wrap ga-2 mb-2">
              <v-icon size="small" class="mr-1">mdi-tag-search-outline</v-icon>
              <strong>{{ unmatched.length }} application(s) we did not recognise</strong>
              <v-spacer />
              <v-btn size="small" variant="tonal" prepend-icon="mdi-download"
                     @click="downloadUnmatched">Download for signature review</v-btn>
            </div>
            <p class="text-caption text-medium-emphasis mb-2">
              These are not findings — we simply have no catalog entry for them. Most will
              be ordinary business software. Send this list back to us and any AI tools
              among them become detectable for every city, not just yours.
            </p>
            <v-alert v-if="result.unmatched_truncated" type="info" variant="tonal"
                     density="compact" class="mb-2">
              Your tenant had more unrecognised applications than we return at once. This
              is the first {{ unmatched.length }}.
            </v-alert>
            <v-table density="compact">
              <thead>
                <tr>
                  <th class="text-left">Application</th>
                  <th class="text-left">Publisher</th>
                  <th class="text-left">Users</th>
                  <th class="text-left">Can reach</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(u, i) in unmatched" :key="i">
                  <td class="text-body-2">
                    {{ u.app_name || '—' }}
                    <v-chip v-if="u.tenant_wide_admin_consent === 'yes'" size="x-small"
                            color="warning" variant="tonal" class="ml-1">tenant-wide</v-chip>
                  </td>
                  <td class="text-caption text-medium-emphasis">{{ u.publisher || '—' }}</td>
                  <td class="text-caption">{{ u.user_count || '—' }}</td>
                  <td class="text-caption text-medium-emphasis">
                    {{ u.scope_sensitivity || '—' }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </template>
        </template>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">{{ phase === 'done' ? 'Close' : 'Cancel' }}</v-btn>
        <v-btn v-if="phase === 'preview'" color="primary" :loading="store.running"
               @click="run">
          {{ dryRun ? 'Run dry run' : 'Write to inventory' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
/**
 * OAuthImportDialog — upload the customer-run OAuth export (Door A) and run shadow-AI
 * discovery. Obeys components → stores → GovernanceService layering.
 *
 * Two deliberate safety behaviours:
 *  - dry run is ON by default, so a first run reports without writing anything;
 *  - employee identities in the file are NEVER uploaded (only per-app counts), even if
 *    the admin exported them.
 */
import { ref, computed, watch } from 'vue'
import { useDiscoveryStore } from '../stores/discovery'
import CopyLine from './CopyLine.vue'

const open  = defineModel({ type: Boolean, default: false })
const props = defineProps({ defaultCity: { type: String, default: '' } })
const emit  = defineEmits(['done'])

const store = useDiscoveryStore()

// Script download + its server-computed checksum. Fetched when the dialog opens so the
// hash shown is always the hash of the file this deployment would hand you.
const scriptMeta = ref(null)
const scriptUrl  = computed(() => store.oauthScriptUrl('microsoft'))

/** 'script' = run our PowerShell export. 'graph' = browser-only, nothing executes. */
const method     = ref('script')
const graphFiles = ref(null)
/** Raw Graph blobs, sent untouched. The browser never interprets tenant data — the
 *  server identifies each file and performs the join. */
const graphBlobs = ref([])

/**
 * Every command the admin needs, in one place so the UI and the manual cannot drift.
 * $top=999 keeps most tenants to a single page; the nextLink warning covers the rest.
 */
const cmd = {
  install: 'Install-Module Microsoft.Graph -Scope CurrentUser',
  hash:    'Get-FileHash .\\Export-EntraOAuthGrants.ps1 -Algorithm SHA256',
  unblock: 'Unblock-File .\\Export-EntraOAuthGrants.ps1',
  policy:  'Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned',
  run:     '.\\Export-EntraOAuthGrants.ps1',
  q1: 'https://graph.microsoft.com/v1.0/servicePrincipals?$select=id,appId,displayName,publisherName,signInAudience&$top=999',
  q2: 'https://graph.microsoft.com/v1.0/oauth2PermissionGrants?$top=999',
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text || '') } catch { /* non-fatal */ }
}

watch(open, async (isOpen) => {
  if (isOpen && !scriptMeta.value) scriptMeta.value = await store.oauthScriptMeta('microsoft')
}, { immediate: true })


const phase        = ref('select')
const file         = ref(null)
const grants       = ref([])
const provider     = ref('')
const fileHasUsers = ref(false)
const dryRun       = ref(true)
const parseError   = ref('')
const runError     = ref('')
const result       = ref({})

const cityName = computed(() => props.defaultCity || 'this city')

async function onFile(f) {
  parseError.value = ''
  grants.value = []
  fileHasUsers.value = false
  const picked = Array.isArray(f) ? f[0] : f
  if (!picked) return
  try {
    const text = await picked.text()
    const data = JSON.parse(text)
    const list = Array.isArray(data) ? data : (data.grants || [])
    if (!Array.isArray(list) || !list.length) {
      parseError.value = 'No "grants" found in this file.'
      return
    }
    provider.value = (data && data.provider) || list[0]?.provider || ''
    fileHasUsers.value = list.some(g => Array.isArray(g.users) && g.users.length)
    // Strip identities client-side: only counts are ever sent.
    grants.value = list.map(g => ({
      app_id:     g.app_id || '',
      app_name:   g.app_name || '',
      publisher:  g.publisher || '',
      provider:   g.provider || provider.value || '',
      scopes:     Array.isArray(g.scopes) ? g.scopes : [],
      user_count: typeof g.user_count === 'number'
        ? g.user_count
        : (Array.isArray(g.users) ? g.users.length : null),
      // Carried, NOT stripped. Identities are the thing we remove (below); these two are
      // risk/attribution metadata about the APP:
      //   tenant_wide_admin_consent - an admin approved it for everyone, so no employee
      //     individually consented. The most serious thing an export can tell you.
      //   sign_in_audience - decides whether this app's ID is portable to other cities.
      tenant_wide_admin_consent: !!g.tenant_wide_admin_consent,
      sign_in_audience: g.sign_in_audience || '',
    }))
    phase.value = 'preview'
  } catch (e) {
    parseError.value = `Could not read this file: ${e.message}`
  }
}

/**
 * Read the two Graph Explorer downloads. We parse only far enough to confirm they are
 * JSON and to reject an obviously wrong file early; CLASSIFICATION AND JOINING HAPPEN ON
 * THE SERVER, so no directory logic lives in the browser.
 */
async function onGraphFiles(f) {
  parseError.value = ''
  graphBlobs.value = []
  fileHasUsers.value = false
  const picked = Array.isArray(f) ? f : (f ? [f] : [])
  if (!picked.length) return
  try {
    const blobs = []
    for (const p of picked) {
      const data = JSON.parse(await p.text())
      if (!data || (!Array.isArray(data.value) && !Array.isArray(data))) {
        parseError.value = `${p.name} does not look like a Graph Explorer result (no "value" array).`
        return
      }
      blobs.push(data)
    }
    if (blobs.length < 2) {
      parseError.value = 'Both downloads are required: servicePrincipals and oauth2PermissionGrants.'
      return
    }
    graphBlobs.value = blobs
    provider.value = 'microsoft'
    phase.value = 'preview'
  } catch (e) {
    parseError.value = `Could not read those files: ${e.message}`
  }
}

async function run() {
  runError.value = ''
  try {
    result.value = await store.runOAuth({
      city: props.defaultCity,
      provider: provider.value || undefined,
      // Exactly one of these is populated, depending on the method chosen.
      grants: method.value === 'script' ? grants.value : [],
      graph_files: method.value === 'graph' ? graphBlobs.value : undefined,
      dry_run: dryRun.value,
    })
    phase.value = 'done'
    // Parent owns the refresh (it knows whether a dry run changed anything).
    emit('done', result.value)
  } catch (e) {
    const code = e.response?.status
    runError.value = code === 503
      ? 'OAuth discovery is disabled. Enable it in Settings.'
      : code === 403
        ? 'OAuth discovery is restricted to administrators.'
        : (e.response?.data?.detail || e.message)
  }
}

/** @type {import('vue').ComputedRef<Array<Object>>} */
const unmatched = computed(() => result.value?.unmatched || [])

/**
 * Save the unrecognised apps so they can be sent back for signature authoring.
 * Deliberately a plain download rather than an automatic upload: the city decides what
 * leaves their environment, and they can open the file and read it first.
 */
function downloadUnmatched() {
  const payload = {
    city: props.defaultCity,
    generated_utc: new Date().toISOString(),
    note: 'Applications not recognised by the AI catalog. App metadata only — contains no user identities.',
    unmatched: unmatched.value,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url
  a.download = `unrecognised-apps-${(props.defaultCity || 'city').toLowerCase().replace(/\s+/g, '-')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function close() {
  open.value = false
  setTimeout(() => {
    phase.value = 'select'; file.value = null; grants.value = []
    graphFiles.value = null; graphBlobs.value = []
    result.value = {}; parseError.value = ''; runError.value = ''
    fileHasUsers.value = false; dryRun.value = true
  }, 300)
}
</script>
