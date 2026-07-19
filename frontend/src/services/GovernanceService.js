/**
 * GovernanceService.js — Single API surface for all backend communication.
 *
 * Architecture rules (PROJECT_INSTRUCTIONS.md):
 *   - Vue components NEVER call this directly — they call Pinia stores.
 *   - Pinia stores NEVER import axios — they call this service.
 *   - This is the ONLY file that knows the backend exists.
 *
 * Swapping backends (Sheets → Firestore → any future source):
 *   Update the axios base URL or replace the http adapter below.
 *   Zero changes required in stores or components.
 *
 * @module GovernanceService
 */

import axios from 'axios'
import { getIdToken } from 'firebase/auth'
import { firebaseAuth } from '../firebase'
import { authToken } from './tokenStore'

const http = axios.create({
  baseURL: '/api',
  timeout: 90000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach a FRESH Firebase ID token to every request.
//
// getIdToken() without forceRefresh returns the SDK's cached token and
// transparently refreshes it when near expiry (Firebase tokens live 60 min).
// The old approach captured the token ONCE at login into tokenStore and never
// refreshed — any session older than an hour started 401ing until a manual
// page reload. tokenStore is kept only as a fallback for the brief window
// before firebaseAuth.currentUser hydrates on page load.
http.interceptors.request.use(async (config) => {
  const fbUser = firebaseAuth.currentUser
  if (fbUser) {
    try {
      config.headers.Authorization = `Bearer ${await getIdToken(fbUser)}`
      return config
    } catch (err) {
      console.warn('[api] getIdToken failed, falling back to cached token:', err?.code || err)
    }
  }
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
})

// One-shot 401 recovery: force-refresh the token and retry the request once.
// Catches clock-skew and just-expired edge cases without user-visible logout.
// Every 401 is logged with timing so intermittent auth failures (e.g. the
// "expires after ~5 min" report of 2026-07-07) leave diagnosable evidence
// in the browser console instead of a mystery.
http.interceptors.response.use(undefined, async (error) => {
  const cfg = error.config || {}
  const status = error.response?.status
  if (status === 401) {
    console.warn(`[api] 401 on ${cfg.method?.toUpperCase()} ${cfg.url} at ${new Date().toISOString()}`,
      { retried: !!cfg._retriedAfter401, detail: error.response?.data?.detail })
  }
  if (status === 401 && !cfg._retriedAfter401 && firebaseAuth.currentUser) {
    cfg._retriedAfter401 = true
    try {
      const fresh = await getIdToken(firebaseAuth.currentUser, /* forceRefresh */ true)
      cfg.headers.Authorization = `Bearer ${fresh}`
      return http.request(cfg)
    } catch (err) {
      console.warn('[api] forced token refresh failed:', err?.code || err)
    }
  }
  return Promise.reject(error)
})

// ─────────────────────────────────────────────────────────────────────────────
// Target Registry
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all active audit targets.
 * @returns {Promise<import('./types').ComplianceTarget[]>}
 */
const getTargets = () => http.get('/targets').then(r => r.data)

/**
 * Add a new target to the registry.
 * @param {import('./types').TargetCreatePayload} payload
 * @returns {Promise<import('./types').ComplianceTarget>}
 */
const createTarget = (payload) => http.post('/targets', payload).then(r => r.data)

/**
 * Soft-delete (deactivate) a target.
 * @param {string} id
 * @returns {Promise<void>}
 */
const deleteTarget = (id) => http.delete(`/targets/${id}`)

/**
 * Bulk-import targets (platform_admin only; 403 otherwise).
 * Rows are validated/deduped server-side; import never scans automatically.
 * @param {Array<{city: string, domain: string, url?: string, jurisdiction?: string,
 *         tags?: string[], cloudflare_protected?: boolean}>} rows
 * @returns {Promise<{added: number, added_cities: string[],
 *          skipped: Array<{row: number, city: string, reason: string}>,
 *          total_submitted: number}>}
 */
const bulkImportTargets = (rows) =>
  http.post('/targets/bulk', { rows }, { timeout: 300000 }).then(r => r.data)

/**
 * Update scan settings on a target (platform_admin only; 403 otherwise).
 * @param {string} id
 * @param {{cloudflare_protected?: boolean, tags?: string[], url?: string}} patch
 */
const updateTarget = (id, patch) =>
  http.patch(`/targets/${encodeURIComponent(id)}`, patch).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Compliance Scorecard
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch all city scorecard rows.
 * @returns {Promise<import('./types').ScorecardRow[]>}
 */
const getScorecard = () => http.get('/scorecard').then(r => r.data)

/**
 * Fetch aggregate KPI summary.
 * @returns {Promise<import('./types').ScorecardSummary>}
 */
const getScorecardSummary = () => http.get('/scorecard/summary').then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Violations & Cure Period
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch violations, optionally filtered.
 * @param {{ status?: string, city?: string }} [params]
 * @returns {Promise<import('./types').Violation[]>}
 */
const getViolations = (params = {}) => http.get('/violations', { params }).then(r => r.data)

/**
 * Fetch a single violation by ID.
 * @param {string} id
 * @returns {Promise<import('./types').Violation>}
 */
const getViolation = (id) => http.get(`/violations/${id}`).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Audit Runs
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Trigger a new audit run (background task).
 * @param {boolean} [demo=false]
 * @returns {Promise<import('./types').AuditRunState>}
 */
const triggerAudit = (demo = false, cityFilter = null, cities = null) => {
  const params = new URLSearchParams({ demo })
  if (cities && cities.length) params.set('cities', cities.join(','))
  else if (cityFilter) params.set('city_filter', cityFilter)
  return http.post(`/audit/run?${params}`).then(r => r.data)
}

// ── AI Use-Case Inventory ─────────────────────────────────────────────────────

/** List AI assets (RBAC-scoped server-side). Optional city filter. */
const getInventory = (city = null) =>
  http.get('/inventory', { params: city ? { city } : {} }).then(r => r.data)

/** Declare an asset the scanner can't see (internal tool, vendor system). */
const declareAsset = (payload) =>
  http.post('/inventory', payload).then(r => r.data)

/** Attest, assign owner, edit context, or retire an asset. */
const updateAsset = (assetKey, patch) =>
  http.patch(`/inventory/${encodeURIComponent(assetKey)}`, patch).then(r => r.data)

/** Merge Sentinel staff-usage telemetry into the registry (platform_admin). */
const syncSentinelUsage = () =>
  http.post('/inventory/sync-sentinel', {}, { timeout: 120000 }).then(r => r.data)

// ── Discovery channels (widen the moat: new sources into the same registry) ───

/**
 * Run procurement / contract discovery: match uploaded vendor/spend rows against
 * the AI tool catalog and merge matches into the inventory as
 * provenance=discovered_procurement. Same registry, cure engine, and artifacts.
 * @param {import('./types').ProcurementRow[]} rows
 * @param {{ default_city?: string, min_confidence?: number }} [opts]
 * @returns {Promise<import('./types').ProcurementDiscoveryResult>}
 */
const runProcurementDiscovery = (rows, opts = {}) =>
  // TODO: auth token attached globally by the request interceptor
  // TODO: server enforces RBAC (platform_admin/agency_admin) + city scoping
  http.post('/discovery/procurement', {
    rows,
    default_city:   opts.default_city || null,
    min_confidence: opts.min_confidence ?? 0.5,
  }, { timeout: 120000 }).then(r => r.data)

/**
 * Run council-agenda discovery for one source (Legistar client, PDF URL, or
 * pasted text) over a date window → discovered_agenda in the registry.
 * Flag-gated server-side (503 if the agenda engine is disabled).
 * @param {import('./types').AgendaDiscoveryRequest} payload
 * @returns {Promise<import('./types').AgendaDiscoveryResult>}
 */
/**
 * Run OAuth / shadow-AI discovery from an uploaded export (or a live sync later).
 * Dry run is the DEFAULT on the server: nothing is written unless dry_run is false.
 * @param {import('./types').OAuthDiscoveryRequest} payload
 * @returns {Promise<import('./types').OAuthDiscoveryResult>}
 */
const runOAuthDiscovery = (payload) =>
  // TODO: validate the caller holds write:discovery for this city (auth placeholder)
  http.post('/discovery/oauth', payload, { timeout: 120000 }).then(r => r.data)

const runAgendaDiscovery = (payload) =>
  // TODO: server enforces RBAC (platform_admin/agency_admin) + city scoping
  http.post('/discovery/agenda', payload, { timeout: 300000 }).then(r => r.data)

// ── Analytics ─────────────────────────────────────────────────────────────────
/** Aggregate compliance + discovery analytics (RBAC-scoped server-side). */
const getAnalytics = () => http.get('/analytics').then(r => r.data)

// ── Admin: operational settings / feature flags (platform_admin only) ─────────
/** @returns {Promise<{settings: Object, schema: Object}>} */
const getAdminSettings  = () => http.get('/admin/settings').then(r => r.data)
/** @param {Object} updates key→value; server validates + audit-logs. */
const saveAdminSettings = (updates) => http.put('/admin/settings', { updates }).then(r => r.data)

// ── Admin: users & agencies ──────────────────────────────────────────────────
const getMe        = ()       => http.get('/auth/me').then(r => r.data)
const getUsers     = ()       => http.get('/auth/users').then(r => r.data)
const upsertUser   = (u)      => http.post('/auth/users', u).then(r => r.data)
const deleteUser   = (email)  => http.delete(`/auth/users/${encodeURIComponent(email)}`).then(r => r.data)
const getAgencies  = ()       => http.get('/agencies').then(r => r.data)
const upsertAgency = (a)      => http.post('/agencies', a).then(r => r.data)

/**
 * Poll the status of the current or last audit run.
 * @returns {Promise<import('./types').AuditRunState>}
 */
const getAuditStatus = () => http.get('/audit/run').then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Audit Log
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch audit log entries (most recent first).
 * @param {number} [limit=100]
 * @returns {Promise<import('./types').AuditLogEntry[]>}
 */
const getAuditLog = (limit = 100) =>
  http.get(`/logs?limit=${limit}`).then(r => r.data)

/**
 * Operational error log (platform-admin only) — what broke, for triage.
 * @param {number} [limit=100]
 * @returns {Promise<Object[]>}
 */
// TODO: attach auth token; backend enforces platform-admin (403 otherwise)
const getErrorLog = (limit = 100) =>
  http.get(`/errors?limit=${limit}`).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Deep Scan (Chrome-assisted capture for Cloudflare-protected sites)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Submit a browser-captured page for compliance analysis.
 * Used by the Deep Scan flow when a city is not_assessed due to Cloudflare/WAF blocking.
 * Set persist=true to write results to Scorecard + Violations sheets.
 *
 * @param {{ url: string, html: string, script_hosts: string[], text: string,
 *           city: string, jurisdiction: string, domain: string, persist: boolean }} capture
 * @returns {Promise<{ detected_assets: object[], open_violations: number, persisted: boolean }>}
 */
const submitDeepScan = (capture) =>
  http.post('/audit/chrome-capture', capture).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Download a TRAIGA compliance report for a city as a .docx Blob.
 * Uses the axios instance so the Bearer token is attached automatically.
 * @param {string} city
 * @returns {Promise<Blob>}
 */
const downloadReport = (city) =>
  http.get('/reports/generate', {
    params: { city },
    responseType: 'blob',
    timeout: 120000,   // report generation can take up to 2 min
  }).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Safe Harbor (Municipal AI Profile — Tex. Bus. & Com. Code § 552.105)
// ─────────────────────────────────────────────────────────────────────────────

/** Readiness checklist + function scores for a city. */
const getSafeHarbor = (city) =>
  http.get(`/safeharbor/${encodeURIComponent(city)}`).then(r => r.data)

/** Attest or clear a control (platform_admin / agency_admin for the city). */
const attestSafeHarbor = (city, controlId, status = 'attested', notes = '') =>
  http.post(`/safeharbor/${encodeURIComponent(city)}/attest`,
            { control_id: controlId, status, notes }).then(r => r.data)

/** Download the NIST AI RMF Alignment Statement (.docx) as a Blob. */
const downloadAlignmentStatement = (city) =>
  http.get(`/safeharbor/${encodeURIComponent(city)}/statement`, {
    responseType: 'blob',
    timeout: 120000,
  }).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// CID — AG Civil Investigative Demand (Tex. Bus. & Com. Code § 552.103-.104)
// ─────────────────────────────────────────────────────────────────────────────

/** Per-asset, per-item 552.103(b) readiness for a city. */
const getCidReadiness = (city) =>
  http.get(`/cid/${encodeURIComponent(city)}/readiness`).then(r => r.data)

/** AG Response Package (.docx) as a Blob. */
const downloadCidPackage = (city) =>
  http.get(`/cid/${encodeURIComponent(city)}/package`,
           { responseType: 'blob', timeout: 120000 }).then(r => r.data)

/** § 552.104(b)(2) Cure Statement (.docx) as a Blob. 404 if nothing cured. */
const downloadCureStatement = (city) =>
  http.get(`/cid/${encodeURIComponent(city)}/cure-statement`,
           { responseType: 'blob', timeout: 120000 }).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Scheduler Status
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch automated scan schedule metadata.
 * @returns {Promise<{
 *   scheduler_running: boolean,
 *   scan_cadence_hours: number,
 *   next_run_utc: string|null,
 *   last_run_utc: string|null,
 *   auto_scan_cities: number,
 *   manual_scan_cities: number,
 *   manual_city_names: string[],
 * }>}
 */
const getScheduleStatus = () => http.get('/audit/schedule').then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Remediation — AI Use Policy generator
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Download a vendor-specific AI Use Policy Word document for a city.
 * @param {string} city
 * @returns {Promise<Blob>}
 */
const downloadPolicy = (city) =>
  http.get('/remediation/policy', {
    params: { city },
    responseType: 'blob',
    timeout: 120000,
  }).then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Sentinel — Internal browser DLP (admin / security role only)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch Sentinel DLP events (metadata only), optionally filtered.
 * @param {{ policy_id?: string, user_id?: string, limit?: number }} [params]
 */
const getSentinelEvents = (params = {}) => http.get('/sentinel/events', { params }).then(r => r.data)

/** Fetch per-device heartbeat health (silent = possible bypass). */
const getSentinelDevices = () => http.get('/sentinel/devices').then(r => r.data)

/** Fetch aggregate Sentinel KPIs (events by policy/site, blocked count, device health). */
const getSentinelSummary = () => http.get('/sentinel/summary').then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Health
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Check API health.
 * @returns {Promise<{ status: string, timestamp: string }>}
 */
const checkHealth = () => http.get('/health').then(r => r.data)

// ─────────────────────────────────────────────────────────────────────────────
// Named export — import { GovernanceService } from '@/services/GovernanceService'
// ─────────────────────────────────────────────────────────────────────────────
export const GovernanceService = {
  // Targets
  getTargets,
  createTarget,
  deleteTarget,
  bulkImportTargets,
  updateTarget,
  // Scorecard
  getScorecard,
  getScorecardSummary,
  // Violations
  getViolations,
  getViolation,
  // Audit
  triggerAudit,
  getAuditStatus,
  getScheduleStatus,
  // AI Use-Case Inventory
  getInventory,
  declareAsset,
  updateAsset,
  syncSentinelUsage,
  // Discovery channels
  runProcurementDiscovery,
  runAgendaDiscovery,
  runOAuthDiscovery,
  // Admin settings
  getAdminSettings,
  saveAdminSettings,
  // Analytics
  getAnalytics,
  // Admin (users & agencies)
  getMe,
  getUsers,
  upsertUser,
  deleteUser,
  getAgencies,
  upsertAgency,
  // Logs
  getAuditLog,
  getErrorLog,
  // Deep Scan
  submitDeepScan,
  // Reports
  downloadReport,
  // Safe Harbor
  getSafeHarbor,
  attestSafeHarbor,
  downloadAlignmentStatement,
  // CID
  getCidReadiness,
  downloadCidPackage,
  downloadCureStatement,
  // Remediation
  downloadPolicy,
  // Sentinel (internal DLP)
  getSentinelEvents,
  getSentinelDevices,
  getSentinelSummary,
  // Health
  checkHealth,
}
