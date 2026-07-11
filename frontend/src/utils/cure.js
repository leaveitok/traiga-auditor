/**
 * cure.js — LIVE cure-clock math.
 *
 * The 60-day TRAIGA cure window (§ 552.104) is a function of TIME, anchored to
 * cure_deadline_utc — NOT of when a scan last ran. The backend stores a
 * days_remaining snapshot each scan, but between scans that snapshot goes stale
 * and the countdown appears frozen. Always DISPLAY the countdown live from the
 * real deadline so it ticks down every day and flips to "expired" on time, even
 * if the next scan hasn't run yet.
 *
 * @param {string|null|undefined} deadlineIso  cure_deadline_utc (ISO 8601)
 * @returns {number|null} whole days remaining (>= 0), or null if no/invalid deadline
 */
export function liveDaysLeft(deadlineIso) {
  if (!deadlineIso) return null
  const ms = new Date(deadlineIso).getTime() - Date.now()
  if (Number.isNaN(ms)) return null
  return Math.max(0, Math.ceil(ms / 86_400_000))
}

/**
 * True when the cure window has elapsed (deadline in the past) — used to show
 * "Expired" live, before the next scan re-marks the record. Fail-safe: an
 * unknown deadline is NOT treated as expired.
 * @param {string|null|undefined} deadlineIso
 * @returns {boolean}
 */
export function isCureExpired(deadlineIso) {
  if (!deadlineIso) return false
  const t = new Date(deadlineIso).getTime()
  return !Number.isNaN(t) && t <= Date.now()
}
