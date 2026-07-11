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
    meta: { title: 'Dashboard', icon: 'mdi-view-dashboard', requiresAuth: true },
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('../views/AnalyticsView.vue'),
    meta: { title: 'Analytics', icon: 'mdi-chart-box', requiresAuth: true },
  },
  {
    path: '/targets',
    name: 'Targets',
    component: () => import('../views/TargetsView.vue'),
    meta: { title: 'Target Registry', icon: 'mdi-city', requiresManage: true },
  },
  {
    path: '/violations',
    name: 'Violations',
    component: () => import('../views/ViolationsView.vue'),
    meta: { title: 'Violations & Cure Periods', icon: 'mdi-alert-circle', requiresAuth: true },
  },
  {
    path: '/inventory',
    name: 'Inventory',
    component: () => import('../views/InventoryView.vue'),
    meta: { title: 'AI Inventory', icon: 'mdi-clipboard-list-outline', requiresAuth: true },
  },
  {
    path: '/sentinel',
    name: 'Sentinel',
    component: () => import('../views/SentinelView.vue'),
    meta: { title: 'Sentinel — Internal AI DLP', icon: 'mdi-shield-lock', requiresAuth: true },
  },
  {
    path: '/logs',
    name: 'AuditLog',
    component: () => import('../views/AuditLogView.vue'),
    meta: { title: 'Audit Log', icon: 'mdi-text-box-outline', requiresAuth: true },
  },
  {
    path: '/errors',
    name: 'Errors',
    component: () => import('../views/ErrorsView.vue'),
    meta: { title: 'Error Log', icon: 'mdi-alert-octagon', requiresManage: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('../views/AdminConsoleView.vue'),
    meta: { title: 'Administration', icon: 'mdi-account-cog', requiresManage: true },
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
    ? `${to.meta.title} — TRAIGA Auditor`
    : 'TRAIGA Auditor'
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

  // Already logged in and trying to hit login → dashboard (scoped per role)
  if (to.path === '/login') {
    return '/dashboard'
  }

  // Management-only route accessed by a viewer → back to dashboard
  if ((to.meta.requiresManage || to.meta.requiresAdmin) && !auth.canManage) {
    return { path: '/dashboard' }
  }

  return true
})

export default router
