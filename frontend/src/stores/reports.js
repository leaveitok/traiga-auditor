/**
 * reports.js — Pinia store for compliance report generation.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * Components call this store; they never import GovernanceService.
 *
 * @module stores/reports
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useReportsStore = defineStore('reports', () => {
  /**
   * City name currently generating a report, or null if idle.
   * @type {import('vue').Ref<string|null>}
   */
  const generating = ref(null)

  /** @type {import('vue').Ref<string|null>} */
  const error = ref(null)

  /**
   * Download a TRAIGA compliance report for the given city as a .docx file.
   * Triggers a browser file-save dialog on success.
   *
   * @param {string} city  Exact city name matching the scorecard row
   * @returns {Promise<boolean>}  true on success, false on failure
   *
   * TODO: attach auth token — GovernanceService axios interceptor handles this automatically.
   * TODO: scope to requesting user's assigned city for city-scoped roles.
   */
  async function download(city) {
    generating.value = city
    error.value = null
    try {
      const blob = await GovernanceService.downloadReport(city)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${city.replace(/\s+/g, '_')}_TRAIGA_Compliance_Report.docx`
      a.click()
      URL.revokeObjectURL(url)
      return true
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      return false
    } finally {
      generating.value = null
    }
  }

  /** @param {string} city */
  const isGenerating = (city) => generating.value === city

  // ── Audience presets + live preview (Reports section) ────────────────────
  const presets = ref([])
  const presetsLoaded = ref(false)
  const preview = ref(null)
  const previewLoading = ref(false)
  const previewError = ref(null)

  /** Load the audience presets once. Never throws — the section must render regardless. */
  async function loadPresets() {
    if (presetsLoaded.value) return presets.value
    try {
      const res = await GovernanceService.getReportPresets()
      presets.value = res.presets || []
      presetsLoaded.value = true
    } catch (e) {
      presets.value = []
    }
    return presets.value
  }

  /** Fetch the BundleModel for the live HTML preview. */
  async function loadPreview(city, preset) {
    previewLoading.value = true
    previewError.value = null
    preview.value = null
    try {
      preview.value = await GovernanceService.getReportPreview(city, preset)
    } catch (e) {
      previewError.value = e.response?.data?.detail || e.message
    } finally {
      previewLoading.value = false
    }
    return preview.value
  }

  const bundleUrl = (city, preset, fmt) => GovernanceService.reportBundleUrl(city, preset, fmt)
  const packageUrl = (city, preset) => GovernanceService.reportPackageUrl(city, preset)

  return { generating, error, download, isGenerating,
           presets, presetsLoaded, loadPresets,
           preview, previewLoading, previewError, loadPreview,
           bundleUrl, packageUrl }
})
