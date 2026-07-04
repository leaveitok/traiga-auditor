<template>
  <v-app>
    <v-main class="d-flex align-center justify-center" style="min-height:100vh; background: linear-gradient(135deg, #1A237E 0%, #283593 60%, #1565C0 100%)">
      <v-card max-width="440" width="100%" class="mx-4 pa-2" rounded="xl" elevation="8">

        <!-- Header -->
        <v-card-item class="pt-6 pb-2 text-center">
          <v-avatar color="primary" size="64" class="mb-3">
            <v-icon size="36" color="white">mdi-shield-check</v-icon>
          </v-avatar>
          <v-card-title class="text-h5 font-weight-bold">AI Transparency Auditor</v-card-title>
          <v-card-subtitle class="mt-1">
            Texas HB 149 / TRAIGA Compliance Platform
          </v-card-subtitle>
        </v-card-item>

        <v-divider class="mx-6" />

        <v-card-text class="px-8 py-6">
          <p class="text-body-2 text-medium-emphasis text-center mb-6">
            Sign in with your municipal Google account to access your city's
            compliance dashboard.
          </p>

          <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">
            {{ error }}
          </v-alert>

          <v-btn
            block
            size="large"
            variant="outlined"
            :loading="loading"
            @click="signIn"
            class="text-none"
          >
            <template #prepend>
              <!-- Google 'G' logo SVG -->
              <svg width="20" height="20" viewBox="0 0 48 48" class="mr-1">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.36-8.16 2.36-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
              </svg>
            </template>
            Continue with Google
          </v-btn>
        </v-card-text>

        <v-card-text class="text-center text-caption text-medium-emphasis pb-6">
          Access is restricted to authorized municipal personnel.<br>
          Cite
          <a href="https://statutes.capitol.texas.gov/Docs/BC/htm/BC.552.htm"
             target="_blank" class="text-primary">Tex. Bus. &amp; Com. Code Ch. 552</a>
        </v-card-text>

      </v-card>
    </v-main>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth    = useAuthStore()
const router  = useRouter()
const loading = ref(false)
const error   = ref(null)

async function signIn() {
  loading.value = true
  error.value   = null
  try {
    await auth.loginWithGoogle()
    // Router guard will redirect to /dashboard (admin) or /portal (city user)
    const dest = auth.isAdmin ? '/dashboard' : '/portal'
    router.push(dest)
  } catch (e) {
    error.value = e.message || 'Sign-in failed. Try again.'
  } finally {
    loading.value = false
  }
}
</script>
