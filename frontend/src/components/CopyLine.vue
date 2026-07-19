<template>
  <div class="d-flex align-center ga-1 copyline rounded px-2 py-1">
    <code class="flex-grow-1 text-caption">{{ text }}</code>
    <v-btn size="x-small" variant="text" :icon="copied ? 'mdi-check' : 'mdi-content-copy'"
           :color="copied ? 'success' : undefined"
           :aria-label="copied ? 'Copied' : 'Copy to clipboard'"
           @click="doCopy" />
  </div>
</template>

<script setup>
/**
 * CopyLine — one command or URL with a copy button.
 *
 * Purely presentational (no store, no service), per the layering rule. It exists because
 * the OAuth instructions ask an administrator to run several exact commands, and a
 * mistyped command is indistinguishable from a broken product to the person running it.
 * Copy-to-clipboard removes that whole class of support call.
 */
import { ref } from 'vue'

const props = defineProps({ text: { type: String, required: true } })
const copied = ref(false)

async function doCopy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    // Clipboard access can be denied (insecure context, permissions policy). The text is
    // visible and selectable either way, so this stays silent rather than alarming.
  }
}
</script>

<style scoped>
.copyline {
  background: rgba(128, 128, 128, 0.10);
  overflow-x: auto;
}
.copyline code {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
