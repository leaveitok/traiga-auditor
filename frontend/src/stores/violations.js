/**
 * violations.js — Pinia store for violations & cure period state.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/violations
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useViolationsStore = defineStore('violations', () => {
  /** @type {import('vue').Ref<import('../services/types').Violation[]>} */
  const items   = ref([])
  const loading = ref(false)
  const error   = ref(null)

  const openCount    = computed(() => items.value.filter(v => v.status === 'in_cure').length)
  const expiredCount = computed(() => items.value.filter(v => v.status === 'expired').length)
  const curedCount   = computed(() => items.value.filter(v => v.status === 'cured').length)

  /**
   * @param {{ status?: string, city?: string }} [params]
   */
  async function fetchViolations(params = {}) {
    loading.value = true
    error.value   = null
    try {
      items.value = await GovernanceService.getViolations(params)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  return { items, loading, error, openCount, expiredCount, curedCount, fetchViolations }
})
