<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Target Registry</div>
        <div class="text-caption text-medium-emphasis">
          Municipal websites queued for compliance auditing
        </div>
      </div>
      <div class="d-flex ga-2">
        <v-btn
          v-if="auth.isPlatformAdmin"
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-upload-multiple"
          @click="bulkDialog = true"
        >
          Bulk Import
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="addDialog = true">
          Add Target
        </v-btn>
      </div>
    </div>

    <v-alert v-if="store.error" type="error" class="mb-4">{{ store.error }}</v-alert>

    <v-card>
      <v-data-table
        :headers="headers"
        :items="store.items"
        :loading="store.loading"
        item-value="id"
        hover
      >
        <template #item.tags="{ item }">
          <v-chip v-for="tag in parseTags(item.tags)" :key="tag"
                  size="x-small" class="mr-1" label>{{ tag }}</v-chip>
        </template>
        <template #item.active="{ item }">
          <v-icon :color="item.active === 'true' || item.active === true ? 'success' : 'error'">
            {{ item.active === 'true' || item.active === true ? 'mdi-check-circle' : 'mdi-close-circle' }}
          </v-icon>
        </template>
        <template #item.cloudflare_protected="{ item }">
          <!-- Platform admins can toggle the WAF flag inline; others see status only -->
          <v-btn v-if="auth.isPlatformAdmin"
                 :icon="isCf(item) ? 'mdi-shield-lock-outline' : 'mdi-shield-outline'"
                 :color="isCf(item) ? 'warning' : 'default'"
                 variant="text" size="small"
                 :title="isCf(item) ? 'WAF-protected — excluded from bulk scans (click to clear)' : 'Mark WAF-protected (exclude from bulk scans)'"
                 @click="toggleCf(item)" />
          <template v-else>
            <v-icon v-if="isCf(item)" color="warning" size="small">mdi-shield-lock-outline</v-icon>
            <span v-else class="text-medium-emphasis text-caption">—</span>
          </template>
        </template>
        <template #item.domain="{ item }">
          <a :href="item.domain" target="_blank" class="text-primary">{{ item.domain }}</a>
        </template>
        <template #item.population="{ item }">
          <span v-if="Number(item.population) > 0">{{ fmtPop(item.population) }}</span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
        <template #item.actions="{ item }">
          <v-btn v-if="auth.isPlatformAdmin" icon="mdi-pencil" size="small" variant="text"
                 title="Edit target" @click="openEdit(item)" />
          <v-btn icon="mdi-delete" size="small" color="error" variant="text"
                 @click="confirmDelete(item)" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Add City Dialog (reusable component) -->
    <AddCityDialog v-model="addDialog" />

    <!-- Bulk CSV Import (platform_admin only; server enforces too) -->
    <BulkImportDialog v-if="auth.isPlatformAdmin" v-model="bulkDialog" />

    <!-- Delete confirmation -->
    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card>
        <v-card-title>Remove Target</v-card-title>
        <v-card-text>
          Remove <strong>{{ deleteTarget?.city }}</strong> from the registry?
          This marks it inactive and stops future scans.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :loading="deleting" @click="doDelete">Remove</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit target (platform_admin only; server enforces + audit-logs every change) -->
    <v-dialog v-model="editDialog" max-width="520">
      <v-card>
        <v-card-title>Edit Target</v-card-title>
        <v-card-subtitle class="text-caption text-medium-emphasis pb-2">
          Changes are written to the Audit Log.
        </v-card-subtitle>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="editForm.city" label="City" density="compact" class="mb-3" />
          <v-text-field v-model="editForm.jurisdiction" label="Jurisdiction" density="compact" class="mb-3" />
          <v-text-field v-model="editForm.domain" label="Domain" density="compact" class="mb-3" />
          <v-text-field v-model="editForm.url" label="Seed URL" density="compact" class="mb-3" />
          <v-text-field v-model="editTagsInput" label="Tags (comma-separated)" density="compact" class="mb-3" />
          <v-text-field v-model.number="editForm.population" label="Population" type="number" min="0" density="compact" class="mb-3" />
          <v-switch v-model="editForm.cloudflare_protected" label="Cloudflare protected" color="warning" density="compact" inset />
          <v-alert v-if="editError" type="error" density="compact" variant="tonal" class="mt-2">{{ editError }}</v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="editSaving" @click="saveEdit">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTargetsStore } from '../stores/targets'
import { useAuthStore } from '../stores/auth'
import AddCityDialog from '../components/AddCityDialog.vue'
import BulkImportDialog from '../components/BulkImportDialog.vue'

const store = useTargetsStore()
const auth  = useAuthStore()

const headers = [
  { title: 'City',         key: 'city',                  sortable: true  },
  { title: 'Jurisdiction', key: 'jurisdiction',          sortable: true  },
  { title: 'Population',   key: 'population',             sortable: true  },
  { title: 'Domain',       key: 'domain',                sortable: false },
  { title: 'CF',           key: 'cloudflare_protected',  sortable: false },
  { title: 'Tags',         key: 'tags',                  sortable: false },
  { title: 'Added',        key: 'added_utc',             sortable: true  },
  { title: 'Active',       key: 'active',                sortable: true  },
  { title: '',             key: 'actions',               sortable: false },
]

const addDialog    = ref(false)
const bulkDialog   = ref(false)
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const deleting     = ref(false)

const parseTags = (raw) => {
  if (Array.isArray(raw)) return raw
  try { return JSON.parse(raw) } catch { return raw?.split(',').map(t => t.trim()).filter(Boolean) || [] }
}

const fmtPop = (p) => Number(p).toLocaleString()

const isCf = (item) =>
  item.cloudflare_protected === true || item.cloudflare_protected === 'true'

async function toggleCf(item) {
  const next = !isCf(item)
  try {
    await store.updateTarget(item.id, { cloudflare_protected: next })
    item.cloudflare_protected = next
  } catch (e) {
    store.error = e.response?.data?.detail || e.message
  }
}

function confirmDelete(item) {
  deleteTarget.value = item
  deleteDialog.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await store.removeTarget(deleteTarget.value.id)
    deleteDialog.value = false
  } finally {
    deleting.value = false
  }
}

// ── Edit target (platform_admin) — sends only changed fields so the audit
// log records real edits; store.updateTarget optimistically patches the row.
const editDialog = ref(false)
const editSaving = ref(false)
const editError  = ref('')
const editTagsInput = ref('')
const editForm = ref({})
let editOriginal = null

function openEdit(item) {
  editOriginal = item
  editForm.value = {
    city: item.city || '',
    jurisdiction: item.jurisdiction || 'TX',
    domain: item.domain || '',
    url: item.url || '',
    population: Number(item.population) || 0,
    cloudflare_protected: isCf(item),
  }
  editTagsInput.value = parseTags(item.tags).join(', ')
  editError.value = ''
  editDialog.value = true
}

async function saveEdit() {
  editSaving.value = true
  editError.value = ''
  const tags = editTagsInput.value.split(',').map(t => t.trim()).filter(Boolean)
  const patch = {}
  if (editForm.value.city !== editOriginal.city) patch.city = editForm.value.city
  if (editForm.value.jurisdiction !== editOriginal.jurisdiction) patch.jurisdiction = editForm.value.jurisdiction
  if (editForm.value.domain !== editOriginal.domain) patch.domain = editForm.value.domain
  if (editForm.value.url !== editOriginal.url) patch.url = editForm.value.url
  if ((Number(editOriginal.population) || 0) !== editForm.value.population) patch.population = editForm.value.population
  if (isCf(editOriginal) !== editForm.value.cloudflare_protected) patch.cloudflare_protected = editForm.value.cloudflare_protected
  if (JSON.stringify(parseTags(editOriginal.tags)) !== JSON.stringify(tags)) patch.tags = tags
  if (Object.keys(patch).length === 0) { editDialog.value = false; editSaving.value = false; return }
  try {
    await store.updateTarget(editOriginal.id, patch)
    Object.assign(editOriginal, patch)
    editDialog.value = false
  } catch (e) {
    editError.value = e.response?.data?.detail || e.message
  } finally {
    editSaving.value = false
  }
}

onMounted(() => store.fetchTargets())
</script>
