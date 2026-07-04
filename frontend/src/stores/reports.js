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

  return { generating, error, download, isGenerating }
})
