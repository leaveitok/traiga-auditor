<template>
  <v-app>
    <!-- Mobile/tablet top bar. On small screens the nav drawer is a TEMPORARY
         overlay, so this bar carries the only way to reach navigation. Hidden on
         desktop, where the drawer is permanent and always visible. -->
    <!-- UI-7: navy chrome in both themes (DESIGN_SYSTEM rule 1) - the bar
         matches the drawer so mobile carries the same brand frame. -->
    <v-app-bar v-if="showNav && mobile" density="compact" flat color="navy">
      <v-app-bar-nav-icon aria-label="Open navigation" @click="drawer = !drawer" />
      <v-app-bar-title class="text-body-1 font-weight-medium">TRAIGA Auditor</v-app-bar-title>
    </v-app-bar>

    <AppNavDrawer v-if="showNav" v-model="drawer" />

    <v-main>
      <!-- UI-6 restrained motion: 150ms fade + 4px rise between views. mode
           out-in so two pages never overlap; prefers-reduced-motion disables
           it entirely (CSS below). Purely presentational - the component tree
           per route is unchanged. -->
      <router-view v-slot="{ Component }">
        <transition name="ov-view" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </v-main>
  </v-app>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useAuthStore } from './stores/auth'
import { useAppTheme } from './composables/useAppTheme'
import AppNavDrawer from './components/AppNavDrawer.vue'

const route = useRoute()
const auth  = useAuthStore()

// Restore the saved theme synchronously in setup so it applies before first paint.
const { restore } = useAppTheme()
restore()

// Hide the nav drawer on the login page (it has its own v-app wrapper)
const showNav = computed(() => route.name !== 'Login')

// Responsive drawer state: open by default on desktop (permanent), closed on
// phones/tablets (overlay) so content gets the full viewport width. Re-evaluated
// when the viewport crosses the breakpoint (rotation, window resize).
const { mobile } = useDisplay()
const drawer = ref(!mobile.value)
watch(mobile, (isMobile) => { drawer.value = !isMobile })

// Start Firebase auth listener — fires onAuthStateChanged once immediately
onMounted(() => auth.init())
</script>

<style>
/* Mobile safety net: content must never force the page to scroll sideways.
   Wide tables scroll inside their own wrapper instead of blowing out the layout,
   and long unbroken strings (URLs, IDs, slugs) wrap rather than overflow. */
.v-main { overflow-x: hidden; }
.v-table__wrapper { overflow-x: auto; }

@media (max-width: 600px) {
  .v-card-title,
  .v-card-subtitle,
  .v-card-text { overflow-wrap: anywhere; }
  /* Long links/domains in tables and cards */
  a { overflow-wrap: anywhere; }
}

/* OpticVector Design System v1: Montserrat marks STRUCTURE (page/card titles,
   the nav lockup); body copy stays on Roboto for data density. !important is
   deliberate - Vuetify's typography utilities set font-family with equal
   specificity and this stylesheet must win regardless of load order. */
.v-card-title,
.v-toolbar-title,
.text-h4, .text-h5, .text-h6,
.ov-lockup {
  font-family: 'Montserrat', 'Roboto', sans-serif !important;
}

/* Stealth contrast (UI-3c): Vuetify's tonal variant paints currentColor at
   var(--v-activated-opacity) (~12%), which reads as DISABLED on the navy
   surfaces (found in the 2026-08-23 live audit). Raise the underlay presence
   for tonal chips/buttons in Stealth ONLY - Light is untouched. */
.v-theme--stealth .v-chip--variant-tonal .v-chip__underlay,
.v-theme--stealth .v-btn--variant-tonal .v-btn__underlay {
  opacity: 0.26;
}

/* Restrained motion (UI-6; docs/DESIGN_SYSTEM.md - Motion): one speed, 150ms,
   ease-out, opacity/transform only - never layout properties. View swaps fade
   and rise 4px; card hover states ease instead of snapping. */
.ov-view-enter-active { transition: opacity 0.15s ease-out, transform 0.15s ease-out; }
.ov-view-leave-active { transition: opacity 0.1s ease-in; }
.ov-view-enter-from { opacity: 0; transform: translateY(4px); }
.ov-view-leave-to { opacity: 0; }
.v-card { transition: border-color 0.15s ease-out, box-shadow 0.15s ease-out; }

/* Motion is a preference, not a requirement (WCAG 2.3.3). */
@media (prefers-reduced-motion: reduce) {
  .ov-view-enter-active,
  .ov-view-leave-active,
  .v-card { transition: none !important; }
  .ov-view-enter-from { transform: none; }
}
</style>
