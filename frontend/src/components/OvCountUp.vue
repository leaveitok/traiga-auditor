<template><span>{{ display }}</span></template>

<script setup>
/*
 * OvCountUp — a stat numeral that counts up to its value (UI-6 delight pass).
 *
 * Honesty contract (docs/DESIGN_SYSTEM.md · Motion): the animation is
 * presentation ONLY — the bound value is always the real figure, the count-up
 * merely eases the paint. Non-numeric values ('—', department names, 'N/A')
 * render verbatim with no animation, and prefers-reduced-motion snaps straight
 * to the final value (WCAG 2.3.3). Numeric STRINGS (a score persisted as
 * "87") are coerced and keep their own decimal precision.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  value: { type: [Number, String], default: '—' },
  duration: { type: Number, default: 500 },   // ms; DESIGN_SYSTEM.md Motion spec
})

const toNum = (v) => {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
  return null
}
const decimalsOf = (v) => {
  const s = String(v)
  const i = s.indexOf('.')
  return i === -1 ? 0 : Math.min(2, s.length - i - 1)
}

// matchMedia is guarded for non-browser (SFC compile / SSR) contexts.
const reduced =
  typeof window !== 'undefined' &&
  window.matchMedia &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

const shown = ref(0)
const target = computed(() => toNum(props.value))
const display = computed(() => {
  if (target.value === null) return props.value // verbatim passthrough
  return shown.value.toFixed(decimalsOf(props.value))
})

let raf = 0
function animate(from, to) {
  cancelAnimationFrame(raf)
  if (reduced || from === to) { shown.value = to; return }
  const t0 = performance.now()
  const dur = Math.max(1, props.duration)
  const step = (now) => {
    const p = Math.min(1, (now - t0) / dur)
    const eased = 1 - Math.pow(1 - p, 3) // ease-out cubic — settles, never bounces
    shown.value = from + (to - from) * eased
    if (p < 1) raf = requestAnimationFrame(step)
    else shown.value = to
  }
  raf = requestAnimationFrame(step)
}

watch(target, (to, from) => {
  if (to === null) { cancelAnimationFrame(raf); return }
  animate(typeof from === 'number' ? shown.value : 0, to)
}, { immediate: true })

onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>
