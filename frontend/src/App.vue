<template>
  <v-app>
    <AppNavDrawer v-if="showNav" />
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import AppNavDrawer from './components/AppNavDrawer.vue'

const route = useRoute()
const auth  = useAuthStore()

// Hide the nav drawer on the login page (it has its own v-app wrapper)
const showNav = computed(() => route.name !== 'Login')

// Start Firebase auth listener — fires onAuthStateChanged once immediately
onMounted(() => auth.init())
</script>
