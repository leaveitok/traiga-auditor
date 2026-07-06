/**
 * inventory.js — Pinia store for the AI Use-Case Inventory.
 *
 * Layering rule: stores call GovernanceService only — never axios directly.
 * @module stores/inventory
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useInventoryStore = defineStore('inventory', () => {
  const assets  = ref([])
  const loading = ref(false)
  const error   = ref(null)

  // KPI counts drive the workflow: "needs attestation" is the to-do list.
  const needsAttestation = computed(() =>
    assets.value.filter(a => a.lifecycle_status === 'discovered').length)
  const attested = computed(() =>
    assets.value.filter(a => a.lifecycle_status === 'attested').length)
  const undisclosed = computed(() =>
    assets.value.filter(a => Number(a.open_violation_count) > 0).length)
  const active = computed(() =>
    assets.value.filter(a => a.lifecycle_status !== 'retired'))

  async function fetchInventory(city = null) {
    loading.value = true
    error.value   = null
    try {
      assets.value = await GovernanceService.getInventory(city)
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function declare(payload) {
    const saved = await GovernanceService.declareAsset(payload)
    const i = assets.value.findIndex(a => a.asset_key === saved.asset_key)
    if (i >= 0) assets.value[i] = saved
    else assets.value.unshift(saved)
    return saved
  }

  async function update(assetKey, patch) {
    const saved = await GovernanceService.updateAsset(assetKey, patch)
    const i = assets.value.findIndex(a => a.asset_key === assetKey)
    if (i >= 0) assets.value[i] = saved
    return saved
  }

  return {
    assets, loading, error,
    needsAttestation, attested, undisclosed, active,
    fetchInventory, declare, update,
  }
})
