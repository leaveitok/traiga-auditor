<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Target Registry</div>
        <div class="text-caption text-medium-emphasis">
          Municipal websites queued for compliance auditing
        </div>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="addDialog = true">
        Add Target
      </v-btn>
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
          <v-icon v-if="item.cloudflare_protected === true || item.cloudflare_protected === 'true'"
                  color="warning" size="small">mdi-shield-lock-outline</v-icon>
          <span v-else class="text-medium-emphasis text-caption">—</span>
        </template>
        <template #item.domain="{ item }">
          <a :href="item.domain" target="_blank" class="text-primary">{{ item.domain }}</a>
        </template>
        <template #item.actions="{ item }">
          <v-btn icon="mdi-delete" size="small" color="error" variant="text"
                 @click="confirmDelete(item)" />
        </template>
      </v-data-table>
    </v-card>

    <!-- Add City Dialog (reusable component) -->
    <AddCityDialog v-model="addDialog" />

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
  </v-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTargetsStore } from '../stores/targets'
import AddCityDialog from '../components/AddCityDialog.vue'

const store = useTargetsStore()

const headers = [
  { title: 'City',         key: 'city',                  sortable: true  },
  { title: 'Jurisdiction', key: 'jurisdiction',          sortable: true  },
  { title: 'Domain',       key: 'domain',                sortable: false },
  { title: 'CF',           key: 'cloudflare_protected',  sortable: false },
  { title: 'Tags',         key: 'tags',                  sortable: false },
  { title: 'Added',        key: 'added_utc',             sortable: true  },
  { title: 'Active',       key: 'active',                sortable: true  },
  { title: '',             key: 'actions',               sortable: false },
]

const addDialog    = ref(false)
const deleteDialog = ref(false)
const deleteTarget = ref(null)
const deleting     = ref(false)

const parseTags = (raw) => {
  try { return JSON.parse(raw) } catch { return raw?.split(',').map(t => t.trim()).filter(Boolean) || [] }
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

onMounted(() => store.fetchTargets())
</script>
