<template>
  <v-card class="fill-height d-flex flex-column">
    <v-card-title class="d-flex align-center">
      <v-icon class="mr-2" color="warning">mdi-timer-sand</v-icon>
      Cure Deadlines
      <v-spacer />
      <v-tooltip location="bottom" max-width="320">
        <template #activator="{ props }">
          <v-icon v-bind="props" size="small" color="grey">mdi-information-outline</v-icon>
        </template>
        Cities with open violations and the days remaining in their 60-day
        statutory cure period (Tex. Bus. &amp; Com. Code Ch. 552). Violations
        uncured at expiry are referable to the Texas Attorney General.
      </v-tooltip>
    </v-card-title>

    <v-card-text class="flex-grow-1 overflow-y-auto">
      <!-- Empty state: nothing in cure — that's the goal state -->
      <div v-if="!inCure.length" class="text-center py-8 text-medium-emphasis">
        <v-icon size="48" color="success" class="mb-2">mdi-shield-check-outline</v-icon>
        <div class="text-body-2">No open cure periods.</div>
        <div class="text-caption">
          Every detected AI asset is either compliant or cured.
        </div>
      </div>

      <template v-else>
        <div
          v-for="row in inCure"
          :key="row.city"
          class="mb-4"
        >
          <div class="d-flex align-center justify-space-between mb-1">
            <router-link
              :to="`/city/${encodeURIComponent(row.city)}`"
              class="text-body-2 font-weight-medium text-decoration-none text-primary"
            >
              {{ row.city }}
            </router-link>
            <v-chip :color="urgencyColor(row.days)" size="small" label variant="flat">
              {{ row.days }} day{{ row.days === 1 ? '' : 's' }} left
            </v-chip>
          </div>
          <v-progress-linear
            :model-value="(row.days / 60) * 100"
            :color="urgencyColor(row.days)"
            height="8"
            rounded
          />
          <div class="text-caption text-medium-emphasis mt-1">
            {{ row.violations }} open violation{{ row.violations === 1 ? '' : 's' }}
            · cure expires {{ row.deadline }}
          </div>
        </div>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup>
/**
 * CureCountdownPanel — replaces the compliance trend chart (2026-07-07).
 *
 * Rationale: a score-over-time line is empty-state theater until many cities
 * have weeks of history. What no competitor dashboard shows — and what makes
 * a scan actionable for a city attorney — is the statutory clock: days left
 * in each 60-day TRAIGA cure window, worst first. Data comes entirely from
 * the scorecard rows already loaded on the dashboard (no new API calls).
 */
import { computed } from 'vue'
import { useScorecardStore } from '../stores/scorecard'
import { liveDaysLeft } from '../utils/cure'

const store = useScorecardStore()

/** Sheets contract: all values may arrive as strings — parse defensively. */
const toInt = (v) => {
  const n = parseInt(v, 10)
  return Number.isFinite(n) ? n : null
}

const inCure = computed(() =>
  (store.rows || [])
    .map((r) => {
      // LIVE: days from the real deadline (deadline - now), NOT the stored snapshot.
      const days = liveDaysLeft(r.min_cure_deadline_utc)
      const violations = toInt(r.open_violations_count)
        ?? (Array.isArray(r.open_violations) ? r.open_violations.length : 0)
      return { city: r.city, days, violations, deadline: fmtDeadline(r.min_cure_deadline_utc) }
    })
    .filter((r) => r.city && r.days !== null && r.violations > 0)
    .sort((a, b) => a.days - b.days)
    .slice(0, 8)   // panel shows the 8 most urgent; full detail lives in Violations view
)

function fmtDeadline(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

const urgencyColor = (days) => (days <= 15 ? 'error' : days <= 30 ? 'warning' : 'success')
</script>
