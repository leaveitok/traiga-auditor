/**
 * tokenStore.js — Lightweight module-level token holder.
 *
 * Avoids a circular dependency between GovernanceService (which needs the
 * token) and the Pinia auth store (which needs GovernanceService).
 * The auth store writes here; GovernanceService reads here.
 */

export let authToken = null

export function setAuthToken(token) {
  authToken = token
}

export function clearAuthToken() {
  authToken = null
}
