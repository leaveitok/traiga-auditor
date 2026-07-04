/**
 * scorecard.js — Pinia store for compliance scorecard state.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/scorecard
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useScorecardStore = defineStore('scorecard', () => {
  /** @type {import('vue').Ref<import('../services/types').ScorecardRow[]>} */
  const rows    = ref([])
  /** @type {import('vue').Ref<import('../services/types').ScorecardSummary|null>} */
  const summary = ref(null)
  const loading = ref(false)
  const error   = ref(null)

  const bandCounts = computed(() => ({
    green: rows.value.filter(r => r.band === 'green').length,
    amber: rows.value.filter(r => r.band === 'amber').length,
    red:   rows.value.filter(r => r.band === 'red').length,
  }))

  async function fetchScorecard() {
    loading.value = true
    error.value   = null
    try {
      const [scorecardData, summaryData] = await Promise.all([
        GovernanceService.getScorecard(),
        GovernanceService.getScorecardSummary(),
      ])
      rows.value    = scorecardData
      summary.value = summaryData
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  return { rows, summary, loading, error, bandCounts, fetchScorecard }
})
