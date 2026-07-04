<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="pt-4 px-6">Add City Target</v-card-title>
      <v-card-subtitle class="px-6 pb-2 text-caption text-medium-emphasis">
        New city will be queued for TRAIGA compliance auditing
      </v-card-subtitle>

      <v-divider />

      <v-card-text class="pt-4">
        <v-form ref="formRef" @submit.prevent="submit">
          <v-text-field
            v-model="form.city"
            label="City Name"
            :rules="[req]"
            density="compact"
            class="mb-3"
            autofocus
          />
          <v-text-field
            v-model="form.jurisdiction"
            label="Jurisdiction"
            :rules="[req]"
            density="compact"
            class="mb-3"
            hint="e.g. TX"
            persistent-hint
          />
          <v-text-field
            v-model="form.domain"
            label="Domain URL"
            :rules="[req, urlRule]"
            density="compact"
            class="mb-3"
            hint="Must start with https://"
            persistent-hint
          />
          <v-text-field
            v-model="form.url"
            label="Seed URL (optional — defaults to domain)"
            density="compact"
            class="mb-3"
          />
          <v-text-field
            v-model="tagsInput"
            label="Tags (comma-separated)"
            density="compact"
            class="mb-4"
          />
          <v-switch
            v-model="form.cloudflare_protected"
            label="Cloudflare protected"
            color="warning"
            density="compact"
            hint="Routes scans through manual Chrome deep scan instead of headless crawler"
            persistent-hint
            inset
          />
        </v-form>

        <v-alert v-if="errorMsg" type="error" density="compact" class="mt-4" closable @click:close="errorMsg = ''">
          {{ errorMsg }}
        </v-alert>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="cancel">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" @click="submit">Add City</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Success snackbar rendered outside the dialog -->
  <v-snackbar v-model="snackbar" color="success" timeout="4000" location="bottom right">
    <v-icon start>mdi-check-circle</v-icon>
    {{ snackbarMsg }}
  </v-snackbar>
</template>

<script setup>
import { ref } from 'vue'
import { useTargetsStore } from '../stores/targets'

const props = defineProps({
  /** Controls dialog open/closed state via v-model */
  modelValue: { type: Boolean, required: true },
})

const emit = defineEmits(['update:modelValue', 'added'])

const store   = useTargetsStore()
const formRef = ref(null)
const saving  = ref(false)
const errorMsg  = ref('')
const snackbar  = ref(false)
const snackbarMsg = ref('')
const tagsInput = ref('')

const defaultForm = () => ({
  city:                '',
  jurisdiction:        'TX',
  domain:              '',
  url:                 '',
  cloudflare_protected: false,
})

const form = ref(defaultForm())

const req     = (v) => !!v || 'Required'
const urlRule = (v) => /^https?:\/\/.+/.test(v) || 'Must start with https://'

function cancel() {
  resetForm()
  emit('update:modelValue', false)
}

function resetForm() {
  form.value  = defaultForm()
  tagsInput.value = ''
  errorMsg.value  = ''
  formRef.value?.resetValidation()
}

async function submit() {
  // TODO: enforce admin-only permission (auth placeholder)
  const { valid } = await formRef.value.validate()
  if (!valid) return

  saving.value = true
  errorMsg.value = ''

  try {
    const newTarget = await store.addTarget({
      ...form.value,
      url:  form.value.url || form.value.domain,
      tags: tagsInput.value.split(',').map(t => t.trim()).filter(Boolean),
    })
    snackbarMsg.value = `${form.value.city} added to the target registry`
    snackbar.value = true
    emit('added', newTarget)
    emit('update:modelValue', false)
    resetForm()
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || e.message || 'Failed to add target'
  } finally {
    saving.value = false
  }
}
</script>
