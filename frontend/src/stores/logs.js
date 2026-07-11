/**
 * logs.js — Pinia store for the append-only audit log.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * (The old api/client.js path had NO auth interceptor, so /logs 401'd in
 * production and the Audit Log + dashboard trend rendered empty. Routing through
 * GovernanceService attaches the per-request Firebase token + 401 retry.)
 * @module stores/logs
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useLogsStore = defineStore('logs', () => {
  const rows    = ref([])
  const loading = ref(false)
  const error   = ref(null)

  async function fetchLogs(limit = 200) {
    loading.value = true
    error.value   = null
    try {
      rows.value = await GovernanceService.getAuditLog(limit)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  return { rows, loading, error, fetchLogs }
})
