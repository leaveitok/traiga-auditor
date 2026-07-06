<template>
  <v-navigation-drawer v-model="drawer" :rail="rail" permanent>

    <!-- Logo / header -->
    <v-list-item
      prepend-icon="mdi-shield-star"
      title="TRAIGA Auditor"
      subtitle="AI Transparency · Texas HB 149"
      nav
    >
      <template #append>
        <v-btn :icon="rail ? 'mdi-chevron-right' : 'mdi-chevron-left'"
               variant="text" @click="rail = !rail" />
      </template>
    </v-list-item>

    <v-divider />

    <!-- Navigation items — filtered by role -->
    <v-list density="compact" nav>
      <v-list-item
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        :prepend-icon="item.icon"
        :title="item.title"
        rounded="lg"
        active-color="primary"
      />
    </v-list>

    <template #append>
      <v-divider />

      <!-- Statute reference link -->
      <v-list density="compact" nav>
        <v-list-item prepend-icon="mdi-scale-balance"
                     title="Tex. Bus. &amp; Com. Code Ch. 552"
                     subtitle="Read the statute"
                     href="https://statutes.capitol.texas.gov/Docs/BC/htm/BC.552.htm"
                     target="_blank"
                     rounded="lg" />
      </v-list>

      <v-divider />

      <!-- User profile + sign out -->
      <v-list density="compact" nav class="py-2">
        <v-list-item rounded="lg">
          <template #prepend>
            <v-avatar :size="rail ? 28 : 36" color="primary">
              <v-img v-if="auth.photoURL" :src="auth.photoURL" />
              <v-icon v-else color="white" :size="rail ? 16 : 20">mdi-account</v-icon>
            </v-avatar>
          </template>
          <v-list-item-title class="text-body-2 font-weight-medium" style="line-height:1.3">
            {{ auth.displayName }}
          </v-list-item-title>
          <v-list-item-subtitle>
            <v-chip size="x-small"
                    :color="auth.isPlatformAdmin ? 'primary' : (auth.isAgencyAdmin ? 'indigo' : 'blue-grey')"
                    label>
              {{ roleLabel }}
            </v-chip>
          </v-list-item-subtitle>
          <template #append>
            <v-tooltip text="Sign out" location="top">
              <template #activator="{ props }">
                <v-btn v-bind="props" icon="mdi-logout" size="small" variant="text"
                       @click="signOut" />
              </template>
            </v-tooltip>
          </template>
        </v-list-item>
      </v-list>
    </template>

  </v-navigation-drawer>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth   = useAuthStore()
const router = useRouter()
const drawer = ref(true)
const rail   = ref(false)

const baseItems = [
  { to: '/dashboard',  icon: 'mdi-view-dashboard',          title: 'Dashboard'      },
  { to: '/inventory',  icon: 'mdi-clipboard-list-outline',  title: 'AI Inventory'   },
  { to: '/violations', icon: 'mdi-alert-circle',            title: 'Violations'     },
  { to: '/sentinel',   icon: 'mdi-shield-lock',             title: 'Sentinel (DLP)' },
]
const manageItems = [
  { to: '/targets',    icon: 'mdi-city',              title: 'Target Registry' },
  { to: '/logs',       icon: 'mdi-text-box-outline',  title: 'Audit Log'       },
  { to: '/admin',      icon: 'mdi-account-cog',       title: 'Administration'  },
]
const settingsItem = { to: '/settings', icon: 'mdi-cog', title: 'Settings' }

const navItems = computed(() => auth.canManage
  ? [...baseItems, ...manageItems, settingsItem]
  : [...baseItems, settingsItem])

const roleLabel = computed(() => ({
  platform_admin: 'Platform Admin', admin: 'Platform Admin',
  agency_admin: 'Agency Admin', viewer: 'Viewer', city: 'Viewer',
}[auth.role] || 'Viewer'))

async function signOut() {
  await auth.logout()
  router.push('/login')
}
</script>
