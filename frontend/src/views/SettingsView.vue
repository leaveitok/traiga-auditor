<template>
  <v-container fluid class="pa-6" max-width="720">
    <div class="text-h5 font-weight-bold mb-2">Settings</div>
    <div class="text-caption text-medium-emphasis mb-6">
      Backend configuration reference — values are set via environment variables on the server.
    </div>

    <v-card class="mb-4">
      <v-card-title prepend-icon="mdi-google-spreadsheet">Google Sheets</v-card-title>
      <v-card-text>
        <v-list density="compact">
          <v-list-item title="SPREADSHEET_ID"
                       subtitle="Set in backend/.env — the ID from your Sheets URL" />
          <v-list-item title="GOOGLE_SERVICE_ACCOUNT_FILE"
                       subtitle="Path to the service-account JSON key file" />
          <v-list-item title="Required Sheets tabs"
                       subtitle="Targets · Scorecard · Violations · AuditLog" />
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-btn prepend-icon="mdi-open-in-new" variant="text"
               href="https://console.cloud.google.com/apis/api/sheets.googleapis.com"
               target="_blank">
          Google Cloud Console
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-card class="mb-4">
      <v-card-title prepend-icon="mdi-api">Backend API</v-card-title>
      <v-card-text>
        <v-list density="compact">
          <v-list-item title="Base URL" subtitle="http://localhost:8000/api  (dev)" />
          <v-list-item title="Docs" subtitle="/api/docs  (Swagger UI)" />
          <v-list-item title="CORS_ORIGINS" subtitle="Set to your Vue dev server + Firebase domain" />
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-btn prepend-icon="mdi-open-in-new" variant="text"
               href="/api/docs" target="_blank">
          Open API Docs
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-card class="mb-4">
      <v-card-title prepend-icon="mdi-firebase">Firebase Hosting</v-card-title>
      <v-card-text>
        <v-list density="compact">
          <v-list-item title="Deploy" subtitle="firebase deploy --only hosting  (from project root)" />
          <v-list-item title="Build" subtitle="cd frontend && npm run build  (output → dist/)" />
          <v-list-item title="Backend" subtitle="Deploy separately — Cloud Run, App Engine, or any VPS" />
        </v-list>
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title prepend-icon="mdi-scale-balance">Legal Notice</v-card-title>
      <v-card-text class="text-body-2">
        Findings are candidate compliance signals derived from externally observable evidence.
        They require human and legal review and are not enforcement determinations.
        Statutory citations reference Texas HB 149 / TRAIGA (Tex. Bus. &amp; Com. Code Ch. 552),
        effective January 1, 2026. Re-validate citations against the enrolled bill before go-live.
      </v-card-text>
    </v-card>

    <!-- API health -->
    <v-card class="mt-4">
      <v-card-title>API Health Check</v-card-title>
      <v-card-text>
        <v-chip :color="health.ok ? 'success' : 'error'" :prepend-icon="health.ok ? 'mdi-check-circle' : 'mdi-alert'">
          {{ health.ok ? `API reachable · ${health.ts}` : health.err || 'Not reachable' }}
        </v-chip>
      </v-card-text>
      <v-card-actions>
        <v-btn prepend-icon="mdi-refresh" variant="text" :loading="health.loading"
               @click="checkHealth">Check</v-btn>
      </v-card-actions>
    </v-card>
  </v-container>
</template>

<script setup>
import { reactive, onMounted } from 'vue'
import { healthApi } from '../api/client'

const health = reactive({ ok: false, ts: null, err: null, loading: false })

async function checkHealth() {
  health.loading = true
  health.err     = null
  try {
    const res    = await healthApi.check()
    health.ok    = true
    health.ts    = new Date(res.data.timestamp).toLocaleTimeString()
  } catch (e) {
    health.ok    = false
    health.err   = e.message
  } finally {
    health.loading = false
  }
}

onMounted(checkHealth)
</script>
