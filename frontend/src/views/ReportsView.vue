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
      human review — not enforcement determinations.
    </p>

    <v-row>
      <!-- Selection column -->
      <v-col cols="12" md="5" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-text>
            <div class="text-overline mb-1">1 · City</div>
            <v-autocomplete
              v-model="city"
              :items="cityNames"
              :loading="sc.loading"
              density="comfortable"
              variant="outlined"
              placeholder="Select a municipality"
              prepend-inner-icon="mdi-city"
              hide-details
              @update:model-value="onChange"
            />
          </v-card-text>
        </v-card>

        <div class="text-overline mb-2">2 · Audience</div>
        <v-card
          v-for="p in store.presets"
          :key="p.key"
          :variant="preset === p.key ? 'flat' : 'outlined'"
          :color="preset === p.key ? 'primary' : undefined"
          class="mb-3 preset-card"
          @click="selectPreset(p.key)"
        >
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
        <v-card variant="outlined" class="preview-wrap">
          <v-toolbar density="comfortable" color="surface" flat>
            <v-toolbar-title class="text-subtitle-2">
              {{ activePreset ? activePreset.title : 'Preview' }}
            </v-toolbar-title>
            <v-spacer />
            <template v-if="canDownload">
              <v-btn size="small" variant="tonal" prepend-icon="mdi-file-pdf-box"
                     :href="store.bundleUrl(city, preset, 'pdf')" download class="mr-2">PDF</v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-file-word-outline"
                     :href="store.bundleUrl(city, preset, 'docx')" download class="mr-2">DOCX</v-btn>
              <v-btn v-if="activePreset?.package" size="small" color="primary" variant="flat"
                     prepend-icon="mdi-folder-zip-outline"
                     :href="store.packageUrl(city, preset)" download>Package</v-btn>
            </template>
          </v-toolbar>
          <v-divider />

          <div class="preview-body">
            <div v-if="!city || !preset" class="preview-empty">
              <v-icon size="48" color="primary" class="mb-3">mdi-file-document-outline</v-icon>
              <div class="text-body-1 mb-1">Pick a city and an audience</div>
              <div class="text-caption text-medium-emphasis">A live, on-brand preview appears here before you download anything.</div>
            </div>
            <div v-else-if="store.previewLoading" class="preview-empty">
              <v-progress-circular indeterminate color="primary" class="mb-3" />
              <div class="text-caption text-medium-emphasis">Building preview…</div>
            </div>
            <v-alert v-else-if="store.previewError" type="warning" variant="tonal" class="ma-4">
              {{ store.previewError }}
            </v-alert>
            <ReportPreview v-else :model="store.preview" />
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
/**
 * ReportsView — the Reports workspace. Components → store → service layering: this view
 * calls the reports store only. Phase 1 is on-demand generation with a live preview; the
 * Evidence-Room history + snapshots arrive in Phase 2.
 */
import { ref, computed, onMounted } from 'vue'
import { useReportsStore } from '../stores/reports'
import { useScorecardStore } from '../stores/scorecard'
import ReportPreview from '../components/ReportPreview.vue'

const store = useReportsStore()
const sc = useScorecardStore()

const city = ref(null)
const preset = ref(null)

const cityNames = computed(() =>
  [...new Set((sc.rows || []).map(r => r.city).filter(Boolean))].sort())
const activePreset = computed(() => store.presets.find(p => p.key === preset.value) || null)
const canDownload = computed(() => !!city.value && !!preset.value && !!store.preview && !store.previewError)

async function refreshPreview() {
  if (city.value && preset.value) await store.loadPreview(city.value, preset.value)
}
function onChange() { refreshPreview() }
function selectPreset(key) { preset.value = key; refreshPreview() }

onMounted(async () => {
  await Promise.all([store.loadPresets(), sc.rows.length ? null : sc.fetchScorecard()])
})
</script>

<style scoped>
.preset-card { cursor: pointer; transition: box-shadow 0.15s; }
.preset-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.12); }
.preview-wrap { overflow: hidden; }
.preview-body { background: #E9EDF2; min-height: 60vh; max-height: 78vh; overflow-y: auto; padding: 24px; }
.preview-empty { display: flex; flex-direction: column; align-items: center; justify-content: center;
                 text-align: center; min-height: 52vh; color: #607D8B; }
</style>
