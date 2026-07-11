/**
 * analytics.js — Pinia store for the Analytics page.
 * Layering: stores call GovernanceService only.
 * @module stores/analytics
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useAnalyticsStore = defineStore('analytics', () => {
  const data    = ref(null)
  const loading = ref(false)
  const error   = ref(null)

  async function fetch() {
    loading.value = true
    error.value   = null
    try {
      data.value = await GovernanceService.getAnalytics()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, fetch }
})
