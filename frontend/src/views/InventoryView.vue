<template>
  <v-container fluid class="pa-6">
    <div class="mb-6">
      <div class="text-h5 font-weight-bold">AI Inventory</div>
      <div class="text-caption text-medium-emphasis">
        {{ auth.isPlatformAdmin
           ? 'Every AI system on record across all agencies — discovered by scans, confirmed by owners'
           : 'Your agency\'s AI systems — discovered by scans, confirmed by your team' }}
      </div>
    </div>
    <AiInventoryPanel />
  </v-container>
</template>

<script setup>
import AiInventoryPanel from '../components/AiInventoryPanel.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>
