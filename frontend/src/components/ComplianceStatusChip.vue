<template>
  <v-chip :color="color" :prepend-icon="icon" label size="small">
    {{ label }}
  </v-chip>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
})

const MAP = {
  compliant:    { color: 'success', icon: 'mdi-check-circle',    label: 'Compliant'     },
  in_cure:      { color: 'warning', icon: 'mdi-clock-alert',     label: 'In Cure'       },
  non_compliant:{ color: 'error',   icon: 'mdi-close-circle',    label: 'Non-Compliant' },
  expired:      { color: 'error',   icon: 'mdi-alert-octagon',   label: 'Expired'       },
  not_assessed: { color: 'default', icon: 'mdi-help-circle',     label: 'Not Assessed'  },
}

const color = computed(() => MAP[props.status]?.color || 'default')
const icon  = computed(() => MAP[props.status]?.icon  || 'mdi-help-circle')
const label = computed(() => MAP[props.status]?.label || props.status)
</script>
