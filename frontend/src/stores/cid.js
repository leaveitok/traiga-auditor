/**
 * cid.js — Pinia store for AG Civil Investigative Demand readiness.
 * Layering rule: components -> this store -> GovernanceService.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useCidStore = defineStore('cid', () => {
  const byCity  = ref({})    // city -> readiness result
  const loading = ref(false)
  const error   = ref(null)

  async function fetchReadiness(city) {
    if (!city) return
    loading.value = true
    error.value = null
    try {
      byCity.value = { ...byCity.value, [city]: await GovernanceService.getCidReadiness(city) }
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  const _save = (blob, name) => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    a.click()
    URL.revokeObjectURL(a.href)
  }

  async function downloadPackage(city) {
    _save(await GovernanceService.downloadCidPackage(city),
          `${city.replace(/ /g, '_')}_AG_Response_Package.docx`)
  }

  async function downloadCureStatement(city) {
    _save(await GovernanceService.downloadCureStatement(city),
          `${city.replace(/ /g, '_')}_Cure_Statement.docx`)
  }

  return { byCity, loading, error, fetchReadiness, downloadPackage, downloadCureStatement }
})
