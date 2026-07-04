<template>
  <div class="d-flex flex-column align-center">
    <v-progress-circular
      :model-value="pct"
      :color="color"
      :size="size"
      :width="5"
    >
      <span :style="`font-size:${size / 4}px`" class="font-weight-bold">
        {{ days !== null ? days : '—' }}
      </span>
    </v-progress-circular>
    <div class="text-caption text-medium-emphasis mt-1">days left</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  days: { type: Number, default: null },
  size: { type: Number, default: 56 },
})

const CURE_DAYS = 60

const pct = computed(() => {
  if (props.days === null) return 0
  return Math.round((props.days / CURE_DAYS) * 100)
})

const color = computed(() => {
  if (props.days === null) return 'grey'
  if (props.days > 30) return 'success'
  if (props.days > 10) return 'warning'
  return 'error'
})
</script>
