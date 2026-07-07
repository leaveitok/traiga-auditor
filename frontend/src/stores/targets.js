/**
 * targets.js — Pinia store for the Target Registry.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/targets
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useTargetsStore = defineStore('targets', () => {
  /** @type {import('vue').Ref<import('../services/types').ComplianceTarget[]>} */
  const items   = ref([])
  const loading = ref(false)
  const error   = ref(null)

  async function fetchTargets() {
    loading.value = true
    error.value   = null
    try {
      items.value = await GovernanceService.getTargets()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  /**
   * @param {import('../services/types').TargetCreatePayload} data
   * @returns {Promise<import('../services/types').ComplianceTarget>}
   */
  async function addTarget(data) {
    const newTarget = await GovernanceService.createTarget(data)
    items.value.push(newTarget)
    return newTarget
  }

  /**
   * @param {string} id
   */
  async function removeTarget(id) {
    await GovernanceService.deleteTarget(id)
    items.value = items.value.filter(t => t.id !== id)
  }

  /**
   * Bulk-import parsed CSV rows (platform_admin only).
   * Refreshes the registry afterwards so new rows appear immediately.
   * @param {Array<object>} rows
   * @returns {Promise<{added: number, added_cities: string[], skipped: Array, total_submitted: number}>}
   */
  async function bulkImport(rows) {
    const result = await GovernanceService.bulkImportTargets(rows)
    await fetchTargets()
    return result
  }

  return { items, loading, error, fetchTargets, addTarget, removeTarget, bulkImport }
})
