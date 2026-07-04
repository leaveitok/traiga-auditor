/**
 * remediation.js — Pinia store for remediation artifact generation.
 *
 * Responsibilities:
 *   - Track per-city policy generation state (loading / error)
 *   - Trigger download via GovernanceService.downloadPolicy()
 *   - Auto-trigger file download in the browser on success
 *
 * Components never call GovernanceService directly — they call this store.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useRemediationStore = defineStore('remediation', () => {
  /** Map of city → true while generating */
  const _generating = ref({})
  /** Map of city → error string (null when clean) */
  const _errors = ref({})

  // ── Computed helpers ──────────────────────────────────────────────────────

  const isGenerating = (city) => !!_generating.value[city]
  const getError     = (city) => _errors.value[city] ?? null

  // ── Actions ───────────────────────────────────────────────────────────────

  /**
   * Generate and download an AI Use Policy .docx for the given city.
   * Triggers a browser file download on success.
   *
   * @param {string} city  — must match a city in the Scorecard sheet
   */
  async function generatePolicy(city) {
    _generating.value = { ..._generating.value, [city]: true }
    _errors.value     = { ..._errors.value,     [city]: null }

    try {
      const blob = await GovernanceService.downloadPolicy(city)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${city.replace(/\s+/g, '_')}_AI_Use_Policy.docx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      const msg = err?.response?.data?.detail ?? err?.message ?? 'Policy generation failed'
      _errors.value = { ..._errors.value, [city]: msg }
      throw err
    } finally {
      _generating.value = { ..._generating.value, [city]: false }
    }
  }

  function clearError(city) {
    _errors.value = { ..._errors.value, [city]: null }
  }

  return {
    isGenerating,
    getError,
    generatePolicy,
    clearError,
  }
})
