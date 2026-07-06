/**
 * admin.js — Pinia store for user & agency administration.
 * Layering: components → store → GovernanceService (never axios directly).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { GovernanceService } from '../services/GovernanceService'

export const useAdminStore = defineStore('admin', () => {
  const users    = ref([])
  const agencies = ref([])
  const loading  = ref(false)
  const error    = ref(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const [u, a] = await Promise.all([
        GovernanceService.getUsers().catch(() => []),
        GovernanceService.getAgencies().catch(() => []),
      ])
      users.value    = u
      agencies.value = a
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
    } finally {
      loading.value = false
    }
  }

  async function saveUser(payload) {
    const saved = await GovernanceService.upsertUser(payload)
    await fetchAll()
    return saved
  }

  async function removeUser(email) {
    await GovernanceService.deleteUser(email)
    users.value = users.value.filter(u => u.email !== email)
  }

  async function saveAgency(payload) {
    const saved = await GovernanceService.upsertAgency(payload)
    await fetchAll()
    return saved
  }

  return { users, agencies, loading, error, fetchAll, saveUser, removeUser, saveAgency }
})
