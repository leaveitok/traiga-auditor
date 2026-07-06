<template>
  <v-app>
    <v-main class="login-main">
      <!-- Split hero: brand story on the left, sign-in on the right -->
      <div class="login-grid">
        <!-- Brand panel -->
        <div class="brand-panel d-none d-md-flex flex-column justify-space-between pa-10">
          <div class="d-flex align-center ga-3">
            <v-avatar color="rgba(255,255,255,0.15)" size="44">
              <v-icon size="26" color="white">mdi-shield-star</v-icon>
            </v-avatar>
            <span class="text-h6 font-weight-bold text-white">TRAIGA Auditor</span>
          </div>

          <div>
            <div class="text-h3 font-weight-bold text-white mb-4" style="line-height:1.15">
              AI transparency,<br>enforced.
            </div>
            <p class="text-body-1 text-white" style="opacity:0.85; max-width:460px">
              Continuous TRAIGA / Texas HB 149 compliance monitoring for
              municipalities — automated AI-disclosure audits, cure-period
              tracking, and browser-level DLP for every agency you serve.
            </p>
            <div class="d-flex flex-wrap ga-6 mt-8">
              <div v-for="s in stats" :key="s.label">
                <div class="text-h5 font-weight-bold text-white">{{ s.value }}</div>
                <div class="text-caption text-white" style="opacity:0.75">{{ s.label }}</div>
              </div>
            </div>
          </div>

          <div class="text-caption text-white" style="opacity:0.6">
            Tex. Bus. &amp; Com. Code Ch. 552 · CJIS · HIPAA-aware
          </div>
        </div>

        <!-- Sign-in panel -->
        <div class="signin-panel d-flex align-center justify-center pa-6">
          <div style="width:100%; max-width:400px">
            <div class="d-md-none d-flex align-center ga-3 mb-8 justify-center">
              <v-avatar color="primary" size="40">
                <v-icon size="24" color="white">mdi-shield-star</v-icon>
              </v-avatar>
              <span class="text-h6 font-weight-bold">TRAIGA Auditor</span>
            </div>

            <h1 class="text-h5 font-weight-bold mb-1">Sign in</h1>
            <p class="text-body-2 text-medium-emphasis mb-6">
              Use your government Google account to continue.
            </p>

            <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-4">
              {{ error }}
            </v-alert>

            <v-btn block size="large" variant="flat" color="primary"
                   :loading="loading" @click="signIn" class="text-none mb-4">
              <template #prepend>
                <span class="google-g d-flex align-center justify-center">
                  <svg width="18" height="18" viewBox="0 0 48 48">
                    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.36-8.16 2.36-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                  </svg>
                </span>
              </template>
              Continue with Google
            </v-btn>

            <p class="text-caption text-medium-emphasis">
              Access is restricted to authorized personnel. New accounts start
              with no access until an administrator grants it.
            </p>
          </div>
        </div>
      </div>
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

const stats = [
  { value: 'HB 149', label: 'TRAIGA aligned' },
  { value: '60-day', label: 'cure tracking' },
  { value: 'Local-first', label: 'DLP scanning' },
]

async function signIn() {
  loading.value = true
  error.value   = null
  try {
    await auth.loginWithGoogle()
    router.push('/dashboard')
  } catch (e) {
    error.value = e.message || 'Sign-in failed. Try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-main { min-height: 100vh; }
.login-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  min-height: 100vh;
}
@media (max-width: 960px) {
  .login-grid { grid-template-columns: 1fr; }
}
.brand-panel {
  background: linear-gradient(150deg, #0D1B5E 0%, #1A3A8F 55%, #1565C0 100%);
  position: relative;
  overflow: hidden;
}
.brand-panel::after {
  content: "";
  position: absolute;
  right: -120px; top: -120px;
  width: 380px; height: 380px;
  background: radial-gradient(circle, rgba(255,255,255,0.10) 0%, transparent 70%);
}
.signin-panel { background: rgb(var(--v-theme-surface)); }
.google-g {
  background: #fff; width: 26px; height: 26px; border-radius: 4px;
}
</style>
