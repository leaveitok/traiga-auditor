<template>
  <v-container fluid class="pa-3 pa-sm-6">
    <div class="d-flex align-center justify-space-between mb-6 flex-wrap ga-3">
      <div>
        <div class="text-h5 font-weight-bold">Administration</div>
        <div class="text-caption text-medium-emphasis">
          {{ auth.isPlatformAdmin ? 'Platform administration — agencies, users, and access grants'
                                  : 'Agency administration — manage users in your agency' }}
        </div>
      </div>
      <v-btn icon="mdi-refresh" variant="text" :loading="store.loading" @click="store.fetchAll" />
    </div>

    <v-alert v-if="store.error" type="error" class="mb-4" closable>{{ store.error }}</v-alert>

    <v-tabs v-model="tab" color="primary" class="mb-4">
      <v-tab value="users"><v-icon start>mdi-account-group</v-icon>Users</v-tab>
      <v-tab v-if="auth.isPlatformAdmin" value="agencies">
        <v-icon start>mdi-domain</v-icon>Agencies
      </v-tab>
    </v-tabs>

    <!-- ── USERS ─────────────────────────────────────────────────────────── -->
    <div v-show="tab === 'users'">
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span class="text-subtitle-1 font-weight-bold">Users &amp; Access</span>
          <v-btn color="primary" prepend-icon="mdi-account-plus" @click="openUser()">
            Invite User
          </v-btn>
        </v-card-title>
        <v-data-table :headers="userHeaders" :items="store.users"
                      :loading="store.loading" item-value="email" hover density="comfortable">
          <template #item.role="{ item }">
            <v-chip size="small" :color="roleColor(item.role)" variant="tonal" label>
              <v-icon start size="14">{{ roleIcon(item.role) }}</v-icon>{{ roleLabel(item.role) }}
            </v-chip>
          </template>
          <template #item.agency_id="{ item }">
            <span class="text-caption">{{ agencyName(item.agency_id) || '—' }}</span>
          </template>
          <template #item.cities="{ item }">
            <div class="d-flex flex-wrap ga-1">
              <template v-if="item.role === 'platform_admin'">
                <v-chip size="x-small" color="primary" variant="flat" label>All cities</v-chip>
              </template>
              <template v-else-if="item.role === 'agency_admin'">
                <v-chip size="x-small" variant="tonal" label>Entire agency</v-chip>
              </template>
              <template v-else>
                <v-chip v-for="c in (item.cities || []).slice(0, 3)" :key="c"
                        size="x-small" variant="tonal" label>{{ shortCity(c) }}</v-chip>
                <v-chip v-if="(item.cities || []).length > 3" size="x-small" label>
                  +{{ item.cities.length - 3 }}
                </v-chip>
                <span v-if="!(item.cities || []).length" class="text-caption text-medium-emphasis">
                  No access granted
                </span>
              </template>
            </div>
          </template>
          <template #item.actions="{ item }">
            <v-btn size="small" variant="text" icon="mdi-pencil" @click="openUser(item)" />
            <v-btn size="small" variant="text" color="error" icon="mdi-delete"
                   :disabled="item.role === 'platform_admin'" @click="confirmDelete(item)" />
          </template>
          <template #no-data>
            <div class="text-center py-8 text-medium-emphasis">
              <v-icon size="40" class="mb-2">mdi-account-group-outline</v-icon>
              <div class="text-body-2">No users yet. Invite your first teammate.</div>
            </div>
          </template>
        </v-data-table>
      </v-card>
    </div>

    <!-- ── AGENCIES (platform admin only) ────────────────────────────────── -->
    <div v-show="tab === 'agencies'">
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span class="text-subtitle-1 font-weight-bold">Agencies</span>
          <v-btn color="primary" prepend-icon="mdi-domain-plus" @click="openAgency()">
            New Agency
          </v-btn>
        </v-card-title>
        <v-data-table :headers="agencyHeaders" :items="store.agencies"
                      :loading="store.loading" item-value="id" hover density="comfortable">
          <template #item.granted_cities="{ item }">
            <div class="d-flex flex-wrap ga-1">
              <v-chip v-for="c in (item.granted_cities || []).slice(0, 4)" :key="c"
                      size="x-small" variant="tonal" label>{{ shortCity(c) }}</v-chip>
              <v-chip v-if="(item.granted_cities || []).length > 4" size="x-small" label>
                +{{ item.granted_cities.length - 4 }}
              </v-chip>
              <span v-if="!(item.granted_cities || []).length"
                    class="text-caption text-medium-emphasis">No cities granted</span>
            </div>
          </template>
          <template #item.actions="{ item }">
            <v-btn size="small" variant="text" icon="mdi-pencil" @click="openAgency(item)" />
          </template>
          <template #no-data>
            <div class="text-center py-8 text-medium-emphasis">
              <v-icon size="40" class="mb-2">mdi-domain</v-icon>
              <div class="text-body-2">No agencies yet. Create one to onboard a municipality.</div>
            </div>
          </template>
        </v-data-table>
      </v-card>
    </div>

    <!-- ── User dialog ───────────────────────────────────────────────────── -->
    <v-dialog v-model="userDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">{{ userForm.email ? 'Edit User' : 'Invite User' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="userForm.email" label="Email (Google account)" type="email"
                        variant="outlined" density="comfortable" :disabled="editingUser"
                        prepend-inner-icon="mdi-email" class="mb-2" />
          <v-select v-model="userForm.role" :items="roleOptions" item-title="label" item-value="value"
                    label="Role" variant="outlined" density="comfortable"
                    prepend-inner-icon="mdi-shield-account" class="mb-2" />
          <v-select v-if="auth.isPlatformAdmin" v-model="userForm.agency_id"
                    :items="store.agencies" item-title="name" item-value="id"
                    label="Agency" variant="outlined" density="comfortable" clearable
                    prepend-inner-icon="mdi-domain" class="mb-2" />
          <v-select v-if="userForm.role === 'viewer'" v-model="userForm.cities"
                    :items="grantableCities" label="City access" multiple chips closable-chips
                    variant="outlined" density="comfortable" prepend-inner-icon="mdi-city"
                    hint="Viewers see only the cities you grant" persistent-hint />
          <v-alert v-else-if="userForm.role === 'agency_admin'" type="info" variant="tonal"
                   density="compact" class="mt-2">
            Agency admins automatically hold every city their agency is granted.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="userDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveUser">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ── Agency dialog ─────────────────────────────────────────────────── -->
    <v-dialog v-model="agencyDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">{{ agencyForm.id ? 'Edit Agency' : 'New Agency' }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="agencyForm.name" label="Agency name" variant="outlined"
                        density="comfortable" prepend-inner-icon="mdi-domain" class="mb-2" />
          <v-select v-model="agencyForm.granted_cities" :items="allCities"
                    label="Granted cities" multiple chips closable-chips variant="outlined"
                    density="comfortable" prepend-inner-icon="mdi-city"
                    hint="Cities this agency's users may be scoped to" persistent-hint />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="agencyDialog = false">Cancel</v-btn>
          <v-btn color="primary" :loading="saving" @click="saveAgency">Save</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card>
        <v-card-title class="text-h6">Remove user?</v-card-title>
        <v-card-text>Remove <strong>{{ deleteTarget?.email }}</strong>? They lose all access immediately.</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">Cancel</v-btn>
          <v-btn color="error" :loading="saving" @click="doDelete">Remove</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3500" location="bottom right">
      {{ snackbar.text }}
    </v-snackbar>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useAdminStore } from '../stores/admin'
import { useAuthStore } from '../stores/auth'
import { GovernanceService } from '../services/GovernanceService'

const store = useAdminStore()
const auth  = useAuthStore()
const tab   = ref('users')

const allCities = ref([])       // every registered target city (for agency grants)
const saving    = ref(false)
const snackbar  = reactive({ show: false, text: '', color: 'success' })

const userDialog   = ref(false)
const agencyDialog = ref(false)
const deleteDialog = ref(false)
const editingUser  = ref(false)
const deleteTarget = ref(null)

const userForm   = ref({ email: '', role: 'viewer', agency_id: null, cities: [] })
const agencyForm = ref({ id: null, name: '', granted_cities: [] })

const userHeaders = [
  { title: 'Email', key: 'email' },
  { title: 'Role', key: 'role' },
  { title: 'Agency', key: 'agency_id' },
  { title: 'City Access', key: 'cities', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]
const agencyHeaders = [
  { title: 'Agency', key: 'name' },
  { title: 'Granted Cities', key: 'granted_cities', sortable: false },
  { title: '', key: 'actions', sortable: false, align: 'end' },
]

const roleOptions = computed(() => {
  const opts = [
    { label: 'Viewer (read-only)', value: 'viewer' },
    { label: 'Agency Admin', value: 'agency_admin' },
  ]
  if (auth.isPlatformAdmin) opts.push({ label: 'Platform Admin', value: 'platform_admin' })
  return opts
})

// Cities a viewer can be granted: the selected agency's grant (platform admin)
// or the current admin's own agency grant (agency admin).
const grantableCities = computed(() => {
  if (auth.isPlatformAdmin) {
    const ag = store.agencies.find(a => a.id === userForm.value.agency_id)
    return ag ? ag.granted_cities : allCities.value
  }
  const own = store.agencies.find(a => a.id === auth.agencyId)
  return own ? own.granted_cities : []
})

const roleLabel = (r) => ({ platform_admin: 'Platform Admin', agency_admin: 'Agency Admin',
  viewer: 'Viewer', admin: 'Platform Admin', city: 'Viewer' }[r] || r)
const roleColor = (r) => ({ platform_admin: 'primary', agency_admin: 'indigo', viewer: 'blue-grey' }[r] || 'default')
const roleIcon  = (r) => ({ platform_admin: 'mdi-shield-crown', agency_admin: 'mdi-shield-account',
  viewer: 'mdi-eye' }[r] || 'mdi-account')
const agencyName = (id) => store.agencies.find(a => a.id === id)?.name || ''
const shortCity  = (c) => String(c).replace(/^City of /, '')

function openUser(item = null) {
  editingUser.value = !!item
  userForm.value = item
    ? { email: item.email, role: item.role, agency_id: item.agency_id || null, cities: [...(item.cities || [])] }
    : { email: '', role: 'viewer', agency_id: auth.isAgencyAdmin ? auth.agencyId : null, cities: [] }
  userDialog.value = true
}

function openAgency(item = null) {
  agencyForm.value = item
    ? { id: item.id, name: item.name, granted_cities: [...(item.granted_cities || [])] }
    : { id: null, name: '', granted_cities: [] }
  agencyDialog.value = true
}

async function saveUser() {
  saving.value = true
  try {
    await store.saveUser({
      email: userForm.value.email.trim(),
      role: userForm.value.role,
      agency_id: userForm.value.agency_id || null,
      cities: userForm.value.role === 'viewer' ? userForm.value.cities : [],
    })
    toast(`${userForm.value.email} saved`)
    userDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

async function saveAgency() {
  saving.value = true
  try {
    await store.saveAgency({ ...agencyForm.value })
    toast(`Agency "${agencyForm.value.name}" saved`)
    agencyDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

function confirmDelete(item) { deleteTarget.value = item; deleteDialog.value = true }
async function doDelete() {
  saving.value = true
  try {
    await store.removeUser(deleteTarget.value.email)
    toast(`${deleteTarget.value.email} removed`)
    deleteDialog.value = false
  } catch (e) { toast(e.response?.data?.detail || e.message, 'error') }
  finally { saving.value = false }
}

function toast(text, color = 'success') { snackbar.text = text; snackbar.color = color; snackbar.show = true }

onMounted(async () => {
  await store.fetchAll()
  try {
    const targets = await GovernanceService.getTargets()
    allCities.value = [...new Set(targets.map(t => t.city))].sort()
  } catch { /* non-fatal */ }
})
</script>
