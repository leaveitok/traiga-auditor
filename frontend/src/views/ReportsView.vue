<template>
  <v-container fluid class="pa-4 pa-md-6">
    <div class="d-flex align-center flex-wrap ga-2 mb-1">
      <v-icon color="primary" class="mr-1">mdi-file-document-multiple-outline</v-icon>
      <h1 class="text-h5 font-weight-bold">Reports</h1>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-5" style="max-width: 760px">
      Generate audience-tailored, defensible evidence bundles from a city's live compliance
      data. Every bundle leads with what was <strong>discovered</strong> versus declared,
      carries a tamper-evident content hash, and frames findings as candidate signals for
      human review — not enforcement determinations. Save a bundle to the
      <strong>Evidence Room</strong> to keep an immutable, reproducible record.
    </p>

    <v-alert v-if="store.actionError" type="warning" variant="tonal" density="compact"
             class="mb-4" closable @click:close="store.actionError = null">
      {{ store.actionError }}
    </v-alert>

    <v-row>
      <!-- Selection column -->
      <v-col cols="12" md="5" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-text>
            <div class="text-overline mb-1">1 · City</div>
            <v-autocomplete
              v-model="city" :items="cityNames" :loading="sc.loading"
              density="comfortable" variant="outlined" placeholder="Select a municipality"
              prepend-inner-icon="mdi-city" hide-details @update:model-value="onCity" />
          </v-card-text>
        </v-card>

        <div class="text-overline mb-2">2 · Audience</div>
        <v-card v-for="p in store.presets" :key="p.key"
                :variant="preset === p.key ? 'flat' : 'outlined'"
                :color="preset === p.key ? 'primary' : undefined"
                class="mb-3 preset-card" @click="selectPreset(p.key)">
          <v-card-text :class="preset === p.key ? 'text-white' : ''">
            <div class="d-flex align-center ga-2 mb-1">
              <v-icon :icon="p.package ? 'mdi-folder-zip-outline' : 'mdi-file-outline'" size="small" />
              <span class="font-weight-bold">{{ p.title }}</span>
              <v-spacer />
              <v-chip size="x-small" :variant="preset === p.key ? 'flat' : 'tonal'"
                      :color="preset === p.key ? 'white' : 'primary'">
                {{ p.package ? 'Package' : p.depth }}
              </v-chip>
            </div>
            <div class="text-caption" :class="preset === p.key ? 'text-white' : 'text-medium-emphasis'">
              For {{ p.audience }} · {{ p.section_count }} sections
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Preview column -->
      <v-col cols="12" md="7" lg="8">
        <v-card variant="outlined" class="preview-wrap mb-4">
          <v-toolbar density="comfortable" color="surface" flat>
            <v-toolbar-title class="text-subtitle-2">
              {{ activePreset ? activePreset.title : 'Preview' }}
            </v-toolbar-title>
            <v-spacer />
            <template v-if="canDownload">
              <v-btn size="small" variant="tonal" prepend-icon="mdi-content-save-outline"
                     :loading="store.busy" class="mr-2" @click="onSave">Save to Evidence Room</v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-file-pdf-box"
                     :loading="store.busy" class="mr-2" @click="store.downloadBundle(city, preset, 'pdf')">PDF</v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-file-word-outline"
                     :loading="store.busy" class="mr-2" @click="store.downloadBundle(city, preset, 'docx')">DOCX</v-btn>
              <v-btn v-if="activePreset?.package" size="small" color="primary" variant="flat"
                     prepend-icon="mdi-folder-zip-outline" :loading="store.busy"
                     @click="store.downloadPackage(city, preset)">Package</v-btn>
            </template>
          </v-toolbar>
          <v-divider />
          <div class="preview-body">
            <div v-if="!city || !preset" class="preview-empty">
              <v-icon size="48" color="primary" class="mb-3">mdi-file-document-outline</v-icon>
              <div class="text-body-1 mb-1">Pick a city and an audience</div>
              <div class="text-caption text-medium-emphasis">A live, on-brand preview appears here before you download or save.</div>
            </div>
            <div v-else-if="store.previewLoading" class="preview-empty">
              <v-progress-circular indeterminate color="primary" class="mb-3" />
              <div class="text-caption text-medium-emphasis">Building preview…</div>
            </div>
            <v-alert v-else-if="store.previewError" type="warning" variant="tonal" class="ma-4">{{ store.previewError }}</v-alert>
            <ReportPreview v-else :model="store.preview" />
          </div>
        </v-card>

        <!-- Evidence Room -->
        <v-card variant="outlined" v-if="city">
          <v-card-title class="d-flex align-center ga-2 text-subtitle-1">
            <v-icon size="small">mdi-archive-outline</v-icon> Evidence Room
            <span class="text-caption text-medium-emphasis">— saved snapshots for {{ city }}</span>
          </v-card-title>
          <v-divider />
          <div v-if="store.snapshotsLoading" class="pa-6 text-center">
            <v-progress-circular indeterminate color="primary" size="24" />
          </div>
          <div v-else-if="!store.snapshots.length" class="pa-6 text-center text-caption text-medium-emphasis">
            No saved snapshots yet. Generate a bundle above and choose <strong>Save to Evidence Room</strong>.
          </div>
          <v-table v-else density="compact">
            <thead>
              <tr>
                <th class="text-left">Saved</th><th class="text-left">Audience</th>
                <th class="text-left">Release</th><th class="text-left">Integrity</th>
                <th class="text-left">Status</th><th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in store.snapshots" :key="s.id">
                <td class="text-caption">{{ shortDate(s.generated_utc) }}</td>
                <td class="text-caption">{{ s.audience || s.preset }}</td>
                <td class="text-caption">{{ s.tool_release }}</td>
                <td class="text-caption"><code>{{ (s.content_sha256 || '').slice(0, 10) }}</code></td>
                <td>
                  <v-chip v-if="s.stale" size="x-small" color="warning" variant="tonal"
                          prepend-icon="mdi-alert-outline">Stale</v-chip>
                  <v-chip v-else size="x-small" color="success" variant="tonal">Current</v-chip>
                </td>
                <td class="text-right">
                  <v-btn size="x-small" variant="text" icon="mdi-file-pdf-box" :loading="store.busy"
                         @click="store.downloadSnapshot(s.id, 'pdf', s.city, s.preset)" />
                  <v-btn size="x-small" variant="text" icon="mdi-file-word-outline" :loading="store.busy"
                         @click="store.downloadSnapshot(s.id, 'docx', s.city, s.preset)" />
                  <v-btn size="x-small" variant="text" icon="mdi-folder-zip-outline" :loading="store.busy"
                         @click="store.downloadSnapshotPackage(s.id, s.city)" />
                  <v-btn v-if="auth.isPlatformAdmin" size="x-small" variant="text" color="error"
                         icon="mdi-delete-outline" :loading="store.busy" @click="confirmDelete(s)" />
                </td>
              </tr>
            </tbody>
          </v-table>
          <v-card-text v-if="store.snapshots.some(s => s.stale)" class="text-caption text-medium-emphasis pt-2">
            <v-icon size="x-small" color="warning">mdi-alert-outline</v-icon>
            A <strong>stale</strong> snapshot was generated before the city's data last changed. It is still a
            valid record of what was true then; generate a fresh one to reflect current findings.
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="3000">{{ snack.text }}</v-snackbar>

    <v-dialog v-model="del.show" max-width="440">
      <v-card>
        <v-card-title class="text-subtitle-1">Tombstone this snapshot?</v-card-title>
        <v-card-text class="text-body-2">
          The snapshot is marked deleted, not destroyed — an auditor can still be shown it existed.
          This requires platform-admin and is recorded in the Audit Log.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="del.show = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" :loading="store.busy" @click="doDelete">Tombstone</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
/**
 * ReportsView — Reports workspace + Evidence Room (Phase 2). Components → store → service.
 * Downloads go through authenticated blob fetches in the store, never plain hrefs, so they
 * work in the deployed app where auth is required.
 */
import { ref, computed, reactive, onMounted } from 'vue'
import { useReportsStore } from '../stores/reports'
import { useScorecardStore } from '../stores/scorecard'
import { useAuthStore } from '../stores/auth'
import ReportPreview from '../components/ReportPreview.vue'

const store = useReportsStore()
const sc = useScorecardStore()
const auth = useAuthStore()

const city = ref(null)
const preset = ref(null)
const snack = reactive({ show: false, text: '', color: 'success' })
const del = reactive({ show: false, target: null })

const cityNames = computed(() =>
  [...new Set((sc.rows || []).map(r => r.city).filter(Boolean))].sort())
const activePreset = computed(() => store.presets.find(p => p.key === preset.value) || null)
const canDownload = computed(() => !!city.value && !!preset.value && !!store.preview && !store.previewError)

function shortDate(iso) { if (!iso) return ''; try { return new Date(iso).toLocaleString() } catch { return iso } }

async function refreshPreview() { if (city.value && preset.value) await store.loadPreview(city.value, preset.value) }
async function onCity() { await Promise.all([refreshPreview(), store.loadSnapshots(city.value)]) }
function selectPreset(key) { preset.value = key; refreshPreview() }

async function onSave() {
  const ok = await store.saveSnapshot(city.value, preset.value)
  Object.assign(snack, { show: true, color: ok ? 'success' : 'error',
    text: ok ? 'Saved to the Evidence Room.' : 'Could not save snapshot.' })
}
function confirmDelete(s) { del.target = s; del.show = true }
async function doDelete() {
  const ok = await store.removeSnapshot(del.target.id, del.target.city)
  del.show = false
  Object.assign(snack, { show: true, color: ok ? 'success' : 'error',
    text: ok ? 'Snapshot tombstoned.' : 'Could not delete snapshot.' })
}

onMounted(async () => {
  await Promise.all([store.loadPresets(), sc.rows.length ? null : sc.fetchScorecard()])
})
</script>

<style scoped>
.preset-card { cursor: pointer; transition: box-shadow 0.15s; }
.preset-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.12); }
.preview-wrap { overflow: hidden; }
.preview-body { background: #E9EDF2; min-height: 52vh; max-height: 70vh; overflow-y: auto; padding: 24px; }
.preview-empty { display: flex; flex-direction: column; align-items: center; justify-content: center;
                 text-align: center; min-height: 44vh; color: #607D8B; }
</style>
