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

  /**
   * Run agenda discovery for one source (Legistar / PDF / pasted text).
   * @param {import('../services/types').AgendaDiscoveryRequest} payload
   * @returns {Promise<import('../services/types').AgendaDiscoveryResult>}
   */
  async function runAgenda(payload) {
    running.value = true
    error.value   = null
    try {
      return await GovernanceService.runAgendaDiscovery(payload)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      running.value = false
    }
  }

  /**
   * Run OAuth / shadow-AI discovery for one city from parsed grant records.
   * @param {import('../services/types').OAuthDiscoveryRequest} payload
   * @returns {Promise<import('../services/types').OAuthDiscoveryResult>}
   */
  async function runOAuth(payload) {
    running.value = true
    error.value   = null
    try {
      return await GovernanceService.runOAuthDiscovery(payload)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      running.value = false
    }
  }

  /**
   * Metadata (incl. SHA-256) for the OAuth export script this deployment serves.
   * Never throws — the dialog must still work if the checksum cannot be read.
   * @returns {Promise<Object|null>}
   */
  async function oauthScriptMeta(provider = 'microsoft') {
    try {
      return await GovernanceService.getOAuthExportScriptMeta(provider)
    } catch (e) {
      return null
    }
  }

  const oauthScriptUrl = (provider = 'microsoft') =>
    GovernanceService.oauthExportScriptUrl(provider)

  return { running, error, runProcurement, runAgenda, runOAuth,
           oauthScriptMeta, oauthScriptUrl }
})
