/**
 * audit.js — Pinia store for audit run state.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/audit
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { GovernanceService } from '../services/GovernanceService'
import { useScorecardStore } from './scorecard'
import { useViolationsStore } from './violations'

export const useAuditStore = defineStore('audit', () => {
  /** @type {import('vue').Ref<import('../services/types').AuditRunStatus>} */
  const status           = ref('idle')
  const startedUtc       = ref(null)
  const finishedUtc      = ref(null)
  const cityCount        = ref(0)
  const observedFailures = ref(0)
  const openViolations   = ref(0)
  const errorMsg         = ref(null)
  /** {current_city, completed, total} while a scan is running */
  const progress         = ref(null)
  let   _pollTimer       = null

  const isRunning = computed(() => status.value === 'running')

  // ── Schedule state ─────────────────────────────────────────────────────────
  const scheduleStatus = ref(null)   // null until first fetch

  async function fetchScheduleStatus() {
    try {
      scheduleStatus.value = await GovernanceService.getScheduleStatus()
    } catch (e) {
      // Non-fatal — schedule panel degrades gracefully if unreachable
      console.warn('[audit store] fetchScheduleStatus failed:', e.message)
    }
  }

  /**
   * @param {boolean} [demo=false]
   */
  async function trigger(demo = false, cityFilter = null) {
    try {
      await GovernanceService.triggerAudit(demo, cityFilter)
      status.value = 'running'
      _startPolling()
    } catch (e) {
      errorMsg.value = e.response?.data?.detail || e.message
    }
  }

  async function refreshStatus() {
    try {
      const d = await GovernanceService.getAuditStatus()
      status.value           = d.status
      startedUtc.value       = d.started_utc
      finishedUtc.value      = d.finished_utc
      cityCount.value        = d.city_count
      observedFailures.value = d.observed_failures
      openViolations.value   = d.open_violations
      errorMsg.value         = d.error
      progress.value         = d.progress ?? null
    } catch (e) {
      errorMsg.value = e.message
    }
  }

  /**
   * Repaint data stores from the backend. The pipeline persists each city's
   * row and violations AS IT FINISHES, so refetching on every poll makes
   * results appear on the dashboard in real time during a long run.
   */
  async function _refreshData() {
    try {
      await Promise.all([
        useScorecardStore().fetchScorecard(),
        useViolationsStore().fetchViolations(),
      ])
    } catch (e) {
      console.warn('[audit store] live data refresh failed:', e.message)
    }
  }

  function _startPolling() {
    if (_pollTimer) clearInterval(_pollTimer)
    _pollTimer = setInterval(async () => {
      await refreshStatus()
      await _refreshData()                       // live repaint every poll
      if (status.value !== 'running') {
        clearInterval(_pollTimer)
        progress.value = null
        await _refreshData()                     // final authoritative repaint
      }
    }, 3000)
  }

  return {
    status, startedUtc, finishedUtc, cityCount,
    observedFailures, openViolations, errorMsg, isRunning, progress,
    scheduleStatus,
    trigger, refreshStatus, fetchScheduleStatus,
  }
})
