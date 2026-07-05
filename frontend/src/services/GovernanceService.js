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
import { authToken } from './tokenStore'

const http = axios.create({
  baseURL: '/api',
  timeout: 90000,
  headers: { 'Content-Type': 'application/json' },
})

// Attach Firebase ID token to every request when available
http.interceptors.request.use((config) => {
  if (authToken) {
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
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
const triggerAudit = (demo = false, cityFilter = null) => {
  const params = new URLSearchParams({ demo })
  if (cityFilter) params.set('city_filter', cityFilter)
  return http.post(`/audit/run?${params}`).then(r => r.data)
}

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
  // Logs
  getAuditLog,
  // Deep Scan
  submitDeepScan,
  // Reports
  downloadReport,
  // Remediation
  downloadPolicy,
  // Sentinel (internal DLP)
  getSentinelEvents,
  getSentinelDevices,
  getSentinelSummary,
  // Health
  checkHealth,
}
