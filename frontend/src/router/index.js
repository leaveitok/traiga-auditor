import { createRouter, createWebHistory } from 'vue-router'
import { watch } from 'vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: 'Sign In', public: true },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: 'Dashboard', icon: 'mdi-view-dashboard', requiresAdmin: true },
  },
  {
    path: '/targets',
    name: 'Targets',
    component: () => import('../views/TargetsView.vue'),
    meta: { title: 'Target Registry', icon: 'mdi-city', requiresAdmin: true },
  },
  {
    path: '/violations',
    name: 'Violations',
    component: () => import('../views/ViolationsView.vue'),
    meta: { title: 'Violations & Cure Periods', icon: 'mdi-alert-circle', requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'AuditLog',
    component: () => import('../views/AuditLogView.vue'),
    meta: { title: 'Audit Log', icon: 'mdi-text-box-outline', requiresAdmin: true },
  },
  {
    path: '/city/:cityName',
    name: 'CityDetail',
    component: () => import('../views/CityDetailView.vue'),
    meta: { title: 'City Detail', icon: 'mdi-city', requiresAuth: true },
  },
  {
    path: '/portal',
    name: 'CityPortal',
    component: () => import('../views/CityPortalView.vue'),
    meta: { title: 'My City', icon: 'mdi-city-variant', requiresAuth: true },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { title: 'Settings', icon: 'mdi-cog', requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} — AI Transparency Auditor`
    : 'AI Transparency Auditor'
})

// ── Auth guard ────────────────────────────────────────────────────────────────
// Lazy-import auth store to avoid circular dependency at module load time.
router.beforeEach(async (to) => {
  // Public routes skip auth entirely
  if (to.meta.public) return true

  const { useAuthStore } = await import('../stores/auth')
  const auth = useAuthStore()

  // Wait for the Firebase onAuthStateChanged listener to fire once
  if (auth.loading) {
    await new Promise((resolve) => {
      const stop = watch(() => auth.loading, (loading) => {
        if (!loading) { stop(); resolve() }
      })
    })
  }

  // Not signed in → send to login
  if (!auth.isAuthenticated) {
    return { path: '/login' }
  }

  // Already logged in and trying to hit login → redirect home
  if (to.path === '/login') {
    return auth.isAdmin ? '/dashboard' : '/portal'
  }

  // Admin-only route accessed by city user → send to portal
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { path: '/portal' }
  }

  return true
})

export default router
