<template>
  <v-app>
    <!-- Mobile/tablet top bar. On small screens the nav drawer is a TEMPORARY
         overlay, so this bar carries the only way to reach navigation. Hidden on
         desktop, where the drawer is permanent and always visible. -->
    <v-app-bar v-if="showNav && mobile" density="compact" flat border>
      <v-app-bar-nav-icon aria-label="Open navigation" @click="drawer = !drawer" />
      <v-app-bar-title class="text-body-1 font-weight-medium">TRAIGA Auditor</v-app-bar-title>
    </v-app-bar>

    <AppNavDrawer v-if="showNav" v-model="drawer" />

    <v-main>
      <router-view />
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
</style>
