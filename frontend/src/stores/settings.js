/**
 * settings.js — Pinia store for admin operational settings / feature flags.
 * Layering: stores call GovernanceService only.
 * @module stores/settings
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref({})
  const schema   = ref({})
  const loading  = ref(false)
  const saving   = ref(false)
  const error    = ref(null)

  async function fetch() {
    loading.value = true
    error.value   = null
    try {
      const r = await GovernanceService.getAdminSettings()
      settings.value = r.settings || {}
      schema.value   = r.schema || {}
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function save(updates) {
    saving.value = true
    error.value  = null
    try {
      const r = await GovernanceService.saveAdminSettings(updates)
      settings.value = r.settings || settings.value
      return settings.value
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      saving.value = false
    }
  }

  return { settings, schema, loading, saving, error, fetch, save }
})
