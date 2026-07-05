/**
 * sentinel.js — Pinia store for AI-GRC Sentinel (internal browser-DLP) telemetry.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * Access note: backing endpoints require admin or 'security' role; city users get 403.
 * @module stores/sentinel
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useSentinelStore = defineStore('sentinel', () => {
  const events  = ref([])
  const devices = ref([])
  const summary = ref(null)
  const loading = ref(false)
  const error   = ref(null)

  const blockedCount = computed(() => events.value.filter(e => e.action_taken === 'blocked').length)
  const silentDevices = computed(() => devices.value.filter(d => d.silent))

  async function fetchAll(params = {}) {
    loading.value = true
    error.value = null
    try {
      const [ev, dv, sm] = await Promise.all([
        GovernanceService.getSentinelEvents(params),
        GovernanceService.getSentinelDevices(),
        GovernanceService.getSentinelSummary(),
      ])
      events.value = ev
      devices.value = dv
      summary.value = sm
    } catch (e) {
      error.value = e.response?.status === 403
        ? 'Sentinel data requires admin or security role.'
        : e.message
    } finally {
      loading.value = false
    }
  }

  return { events, devices, summary, loading, error, blockedCount, silentDevices, fetchAll }
})
