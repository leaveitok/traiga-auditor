/**
 * auth.js — Pinia store for Firebase authentication state.
 *
 * Roles:
 *   admin  → full dashboard, can audit any city
 *   city   → city portal only, can only audit their assigned city
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  getIdToken,
} from 'firebase/auth'
import { firebaseAuth, googleProvider } from '../firebase'
import { setAuthToken, clearAuthToken } from '../services/tokenStore'

export const useAuthStore = defineStore('auth', () => {
  const user      = ref(null)   // Firebase User object
  const role      = ref(null)   // 'platform_admin' | 'agency_admin' | 'viewer' | null
  const city      = ref(null)   // legacy single city (first of cities)
  const cities    = ref([])     // granted cities for scoped users
  const agencyId  = ref(null)   // tenant agency
  const loading   = ref(true)   // true until onAuthStateChanged fires once

  const isPlatformAdmin = computed(() =>
    role.value === 'platform_admin' || role.value === 'admin')   // 'admin' = legacy
  const isAgencyAdmin   = computed(() => role.value === 'agency_admin')
  const canManage       = computed(() => isPlatformAdmin.value || isAgencyAdmin.value)
  // Legacy alias kept for existing route guards / templates.
  const isAdmin         = computed(() => canManage.value)
  const isAuthenticated = computed(() => !!user.value)
  const displayName     = computed(() => user.value?.displayName || user.value?.email || '')
  const photoURL        = computed(() => user.value?.photoURL || null)

  // ── Actions ────────────────────────────────────────────────────────────────

  async function loginWithGoogle() {
    const result  = await signInWithPopup(firebaseAuth, googleProvider)
    const idToken = await getIdToken(result.user)
    user.value    = result.user
    setAuthToken(idToken)
    await _fetchProfile(idToken)
  }

  async function logout() {
    await signOut(firebaseAuth)
    user.value  = null
    role.value    = null
    city.value    = null
    cities.value  = []
    agencyId.value = null
    clearAuthToken()
  }

  /** Refresh the ID token (Firebase tokens expire after 1 hour). */
  async function refreshToken() {
    if (!user.value) return
    const idToken = await getIdToken(user.value, /* forceRefresh */ true)
    setAuthToken(idToken)
    return idToken
  }

  // ── Internal helpers ───────────────────────────────────────────────────────

  async function _fetchProfile(idToken) {
    try {
      const resp = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${idToken}` },
      })
      if (resp.ok) {
        const data = await resp.json()
        role.value   = data.role
        cities.value = data.cities || []
        agencyId.value = data.agency_id || null
        city.value   = data.city || (data.cities && data.cities[0]) || null
      } else {
        const body = await resp.json().catch(() => ({ detail: resp.statusText }))
        console.warn('[auth] /api/auth/me returned', resp.status, body)
        // If backend is unreachable or token verification fails in dev,
        // fall back to checking admin email list client-side
        const ADMIN_EMAILS = (import.meta.env.VITE_ADMIN_EMAILS || 'leaveitok@gmail.com')
          .split(',').map(e => e.trim().toLowerCase())
        const email = user.value?.email?.toLowerCase() || ''
        role.value = ADMIN_EMAILS.includes(email) ? 'admin' : null
        city.value = null
      }
    } catch (err) {
      console.warn('[auth] _fetchProfile error:', err)
      // Backend unreachable — fall back to client-side admin check
      const ADMIN_EMAILS = (import.meta.env.VITE_ADMIN_EMAILS || 'leaveitok@gmail.com')
        .split(',').map(e => e.trim().toLowerCase())
      const email = user.value?.email?.toLowerCase() || ''
      role.value = ADMIN_EMAILS.includes(email) ? 'admin' : null
      city.value = null
    }
  }

  /** Called once from main.js — subscribes to Firebase auth state. */
  function init() {
    onAuthStateChanged(firebaseAuth, async (firebaseUser) => {
      if (firebaseUser) {
        user.value    = firebaseUser
        const idToken = await getIdToken(firebaseUser)
        setAuthToken(idToken)
        await _fetchProfile(idToken)
      } else {
        user.value   = null
        role.value   = null
        city.value   = null
        cities.value = []
        agencyId.value = null
        clearAuthToken()
      }
      loading.value = false
    })
  }

  return {
    // State
    user, role, city, cities, agencyId, loading,
    // Computed
    isAdmin, isPlatformAdmin, isAgencyAdmin, canManage,
    isAuthenticated, displayName, photoURL,
    // Actions
    loginWithGoogle, logout, refreshToken, init,
  }
})
