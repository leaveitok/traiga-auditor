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
          <p class="text-body-2 mb-3">
            Upload the JSON produced by the read-only export script your IT admin ran
            (<code>Export-EntraOAuthGrants.ps1</code>). It lists the third-party apps staff
            consented to; we match them against the AI catalog and record what each grant
            can <strong>reach</strong>. Nothing is fetched from your tenant by this page.
          </p>

          <v-file-input
            v-model="file"
            label="Select the exported .json file"
            accept=".json,application/json"
            prepend-icon="mdi-code-json"
            density="comfortable"
            :error-messages="parseError"
            @update:model-value="onFile"
          />

          <v-switch
            v-model="dryRun"
            color="primary"
            density="compact"
            hide-details
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
            <strong>{{ grants.length }}</strong> application(s) found in the file for
            <strong>{{ cityName }}</strong>.
            {{ dryRun ? 'Dry run: nothing will be written.' : 'Results WILL be written to the inventory.' }}
          </v-alert>

          <v-table density="compact" class="mb-2">
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
          <p v-if="grants.length > 25" class="text-caption text-medium-emphasis">
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
import { ref, computed } from 'vue'
import { useDiscoveryStore } from '../stores/discovery'

const open  = defineModel({ type: Boolean, default: false })
const props = defineProps({ defaultCity: { type: String, default: '' } })
const emit  = defineEmits(['done'])

const store = useDiscoveryStore()

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

async function run() {
  runError.value = ''
  try {
    result.value = await store.runOAuth({
      city: props.defaultCity,
      provider: provider.value || undefined,
      grants: grants.value,
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
    result.value = {}; parseError.value = ''; runError.value = ''
    fileHasUsers.value = false; dryRun.value = true
  }, 300)
}
</script>
