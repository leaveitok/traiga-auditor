/**
 * types.js — Shared JSDoc type definitions for the AI Transparency Auditor.
 *
 * Interface-first principle: all types are defined here before any
 * implementation. When migrating to TypeScript, these become .ts interfaces
 * with zero logic changes.
 *
 * These types represent the API contract between the Vue frontend and the
 * FastAPI backend. They are backend-agnostic — the frontend does not know
 * or care whether data comes from Google Sheets, Firestore, or PostgreSQL.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Target Registry
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A municipal website registered as an audit target.
 * @typedef {Object} ComplianceTarget
 * @property {string}   id           - Short UUID (8 chars)
 * @property {string}   city         - Municipality name
 * @property {string}   jurisdiction - State abbreviation (e.g. "TX")
 * @property {string}   domain       - Root domain (https://...)
 * @property {string}   url          - Crawl seed URL
 * @property {string[]} tags         - Descriptive tags (e.g. ["home_jurisdiction"])
 * @property {string}   added_utc    - ISO 8601 timestamp
 * @property {boolean}  active       - false = soft-deleted
 * @property {number}   [population]  - Municipal population (0 if unknown)
 */

/**
 * Payload for creating a new target.
 * @typedef {Object} TargetCreatePayload
 * @property {string}   city
 * @property {string}   jurisdiction
 * @property {string}   domain
 * @property {string}   [url]         - Defaults to domain if omitted
 * @property {string[]} [tags]
 * @property {number}   [population]  - Municipal population (optional; 0 if unknown)
 */

// ─────────────────────────────────────────────────────────────────────────────
// Compliance Scorecard
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @typedef {'compliant'|'in_cure'|'non_compliant'|'expired'|'no_ai_detected'|'review_needed'|'scan_failed'|'not_assessed'} TraigaStatus
 */

/**
 * @typedef {'green'|'amber'|'red'} ComplianceBand
 */

/**
 * A detected AI asset on a target page.
 * @typedef {Object} AiAsset
 * @property {string}   vendor_id          - e.g. "citibot", "civicplus"
 * @property {string}   display_name
 * @property {string[]} asset_type         - e.g. ["chatbot", "virtual_assistant"]
 * @property {number}   match_confidence   - 0.0–1.0
 * @property {string}   page_url
 * @property {string}   verification_status
 */

/**
 * One row in the compliance scorecard — one entry per city.
 * @typedef {Object} ScorecardRow
 * @property {string}       city
 * @property {string}       jurisdiction
 * @property {string}       domain
 * @property {AiAsset[]}    ai_assets
 * @property {TraigaStatus} traiga_status
 * @property {number}       open_violations_count
 * @property {number|null}  min_days_remaining
 * @property {number}       compliance_score       - 0–100
 * @property {ComplianceBand} band
 * @property {string}       last_scanned_utc
 * @property {boolean}      [last_scan_via_proxy]  - true if the last scan used the paid residential proxy
 */

/**
 * Aggregate KPI summary across all cities.
 * @typedef {Object} ScorecardSummary
 * @property {number}       total_cities
 * @property {number}       compliant
 * @property {number}       in_cure
 * @property {number}       non_compliant
 * @property {number}       expired
 * @property {number}       not_assessed
 * @property {number}       no_ai_detected
 * @property {number}       scan_failed
 * @property {number|null}  average_compliance_score
 */

// ─────────────────────────────────────────────────────────────────────────────
// Violations & Cure Period
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @typedef {'in_cure'|'expired'|'cured'} ViolationStatus
 */

/**
 * @typedef {'high'|'medium'|'low'} ViolationSeverity
 */

/**
 * Evidence captured at the time a violation was first observed.
 * @typedef {Object} ViolationEvidence
 * @property {string}   page_url
 * @property {string[]} matched_indicators
 * @property {string}   remediation
 */

/**
 * A single compliance violation with its 60-day cure period state.
 * @typedef {Object} Violation
 * @property {string}           violation_id
 * @property {string}           city
 * @property {string}           domain
 * @property {string}           asset_id
 * @property {string}           vendor_id
 * @property {string}           [vendor_display_name] - Friendly name resolved from schema (e.g. "Citibot")
 * @property {string}           [asset_type]          - e.g. "chatbot / virtual assistant"
 * @property {string}           [finding_summary]     - Reviewer-facing sentence, e.g. "This site uses Citibot (chatbot)."
 * @property {string[]}         [matched_signals]     - Plain-English list of signature types that fired
 * @property {string}           rule_id           - e.g. "ETM-001"
 * @property {string}           citation          - Statutory reference
 * @property {ViolationSeverity} severity
 * @property {string}           first_observed_utc
 * @property {string}           cure_deadline_utc
 * @property {string}           last_observed_utc
 * @property {number|null}      days_remaining
 * @property {boolean}          cure_period_status
 * @property {ViolationStatus}  status
 * @property {ViolationEvidence} evidence
 * @property {boolean}          needs_human_review
 * @property {string}           [cured_utc]
 */

// ─────────────────────────────────────────────────────────────────────────────
// Audit Log
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A single entry in the append-only audit log.
 * @typedef {Object} AuditLogEntry
 * @property {string} timestamp_utc
 * @property {string} event           - e.g. "scan_complete"
 * @property {number} city_count
 * @property {number} failures
 * @property {Object} details
 */

// ─────────────────────────────────────────────────────────────────────────────
// Audit Run
// ─────────────────────────────────────────────────────────────────────────────

/**
 * @typedef {'idle'|'running'|'completed'|'error'} AuditRunStatus
 */

/**
 * State of the current or last audit run.
 * @typedef {Object} AuditRunState
 * @property {AuditRunStatus} status
 * @property {string|null}    started_utc
 * @property {string|null}    finished_utc
 * @property {number}         city_count
 * @property {number}         observed_failures
 * @property {number}         open_violations
 * @property {string|null}    error
 */

// ─────────────────────────────────────────────────────────────────────────────
// Discovery — Procurement channel
// ─────────────────────────────────────────────────────────────────────────────

/**
 * One parsed row from an uploaded vendor / spend / contract file.
 * @typedef {Object} ProcurementRow
 * @property {string}  vendor        - vendor / supplier name (required)
 * @property {string}  [city]        - owning city (required unless default_city supplied)
 * @property {string}  [contract_id]
 * @property {string}  [amount]
 * @property {string}  [term]
 * @property {string}  [department]
 */

/**
 * Result of a procurement discovery run.
 * @typedef {Object} ProcurementDiscoveryResult
 * @property {number}   written  - assets merged into the AI inventory
 * @property {number}   matched  - rows confidently matched to an AI tool
 * @property {number}   [candidates] - AI-keyword hits flagged for human review
 * @property {number}   skipped  - rows with no confident AI match / missing fields
 * @property {number}   rows     - total rows submitted
 * @property {string[]} cities   - cities that received new/updated assets
 * @property {string[]} errors   - per-row write errors (should be empty)
 */

/**
 * Request to run council-agenda discovery (one source per call).
 * @typedef {Object} AgendaDiscoveryRequest
 * @property {string}  city
 * @property {string}  [legistar_client] - Legistar client slug (e.g. "cityoflewisville")
 * @property {string}  [pdf_url]          - agenda PDF URL (OnBase / CivicPlus etc.)
 * @property {string}  [agenda_text]      - pasted agenda text
 * @property {string}  [since]            - YYYY-MM-DD (date window start)
 * @property {string}  [until]            - YYYY-MM-DD (date window end)
 */

/**
 * Result of an agenda discovery run (procurement shape + which extractor ran).
 * @typedef {Object} AgendaDiscoveryResult
 * @property {number}   written  - assets merged into the AI inventory
 * @property {number}   matched  - items confidently matched to an AI tool
 * @property {number}   [candidates] - AI-keyword hits flagged for human review
 * @property {number}   skipped  - items with no confident AI match / missing fields
 * @property {number}   rows     - total gated items processed
 * @property {string[]} cities   - cities that received new/updated assets
 * @property {string[]} errors   - per-item write errors (should be empty)
 * @property {('vertex'|'vertex_partial'|'keyword_fallback'|'keyword'|'preextracted'|'none')} [extractor]
 *           - which extractor actually produced the items (surfaces the silent
 *             Vertex→keyword fail-open without needing GCP logs)
 */

export {}
