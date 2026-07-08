/**
 * safeharbor.js — Pinia store for TRAIGA safe-harbor readiness (Municipal AI Profile).
 *
 * Layering rule: components call this store; the store calls GovernanceService.
 * State is per-city keyed so the panel works on any CityDetailView instance.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useSafeHarborStore = defineStore('safeharbor', () => {
  const byCity  = ref({})     // city -> readiness result
  const loading = ref(false)
  const error   = ref(null)

  async function fetchReadiness(city) {
    loading.value = true
    error.value = null
    try {
      byCity.value = { ...byCity.value, [city]: await GovernanceService.getSafeHarbor(city) }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function attest(city, controlId, status, notes) {
    await GovernanceService.attestSafeHarbor(city, controlId, status, notes)
    await fetchReadiness(city)   // re-derive scores after every change
  }

  async function downloadStatement(city) {
    const blob = await GovernanceService.downloadAlignmentStatement(city)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${city.replace(/ /g, '_')}_Alignment_Statement.docx`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return { byCity, loading, error, fetchReadiness, attest, downloadStatement }
})
