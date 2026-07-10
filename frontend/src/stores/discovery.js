/**
 * discovery.js — Pinia store for discovery channels (procurement, later OAuth/network).
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/discovery
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useDiscoveryStore = defineStore('discovery', () => {
  const running = ref(false)
  const error   = ref(null)

  /**
   * Run procurement discovery over parsed rows.
   * @param {import('../services/types').ProcurementRow[]} rows
   * @param {{ default_city?: string, min_confidence?: number }} [opts]
   * @returns {Promise<import('../services/types').ProcurementDiscoveryResult>}
   */
  async function runProcurement(rows, opts = {}) {
    running.value = true
    error.value   = null
    try {
      return await GovernanceService.runProcurementDiscovery(rows, opts)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      running.value = false
    }
  }

  return { running, error, runProcurement }
})
