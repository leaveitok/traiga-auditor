/**
 * errors.js — Pinia store for the operational Error Log (admin only).
 * Layering: stores call GovernanceService only.
 * @module stores/errors
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useErrorsStore = defineStore('errors', () => {
  const entries = ref([])
  const loading = ref(false)
  const error   = ref(null)

  async function fetch(limit = 100) {
    loading.value = true
    error.value   = null
    try {
      entries.value = await GovernanceService.getErrorLog(limit)
    } catch (e) {
      // 403 => not a platform admin; surface a friendly message.
      error.value = e.response?.status === 403
        ? 'Platform administrator access required.'
        : (e.response?.data?.detail || e.message)
    } finally {
      loading.value = false
    }
  }

  return { entries, loading, error, fetch }
})
