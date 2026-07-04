/**
 * client.js — Axios API client for the FastAPI backend.
 * All endpoints are prefixed with /api (proxied by Vite in dev,
 * served directly from the same origin in production).
 */
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Targets ──────────────────────────────────────────────────────────────────
export const targetsApi = {
  list:   ()           => http.get('/targets'),
  create: (data)       => http.post('/targets', data),
  remove: (id)         => http.delete(`/targets/${id}`),
}

// ── Audit ────────────────────────────────────────────────────────────────────
export const auditApi = {
  trigger: (demo = false) => http.post(`/audit/run?demo=${demo}`),
  status:  ()             => http.get('/audit/run'),
}

// ── Scorecard ────────────────────────────────────────────────────────────────
export const scorecardApi = {
  list:    () => http.get('/scorecard'),
  summary: () => http.get('/scorecard/summary'),
}

// ── Violations ───────────────────────────────────────────────────────────────
export const violationsApi = {
  list:   (params = {}) => http.get('/violations', { params }),
  detail: (id)          => http.get(`/violations/${id}`),
}

// ── Audit Logs ───────────────────────────────────────────────────────────────
export const logsApi = {
  list: (limit = 100) => http.get(`/logs?limit=${limit}`),
}

// ── Health ───────────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => http.get('/health'),
}
