import { create } from 'zustand'
import {
  ApiError,
  acceptInvite,
  bootstrapSetup,
  ensureOrg,
  getAccessToken,
  getMe,
  getSetupStatus,
  isDemoMode,
  listOrgs,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  setAccessToken,
  setStoredOrgId,
  setUnauthorizedHandler,
  type Org,
  type SetupStatus,
} from '@/lib/api'

export type AuthUser = { id: string; email: string; is_superuser?: boolean }

interface AuthState {
  ready: boolean
  demoMode: boolean
  user: AuthUser | null
  org: Org | null
  orgs: Org[]
  loginOpen: boolean
  setupOpen: boolean
  setupStatus: SetupStatus | null
  pendingInvite: string | null
  busy: boolean
  error: string | null

  bootstrap: () => Promise<void>
  setLoginOpen: (v: boolean) => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  completeSetup: (payload: {
    email: string
    password: string
    org_name: string
    org_slug: string
  }) => Promise<void>
  switchOrg: (orgId: string) => Promise<void>
  refreshOrgs: () => Promise<void>
  setPendingInvite: (token: string | null) => void
  consumePendingInvite: () => Promise<void>
  logout: () => void
  clearError: () => void
}

async function loadSession(email: string): Promise<{ user: AuthUser; org: Org; orgs: Org[] }> {
  const me = await getMe()
  const orgs = await listOrgs()
  let org: Org
  if (orgs.length === 0) {
    org = await ensureOrg(email)
  } else {
    org = await ensureOrg(email)
  }
  const refreshed = await listOrgs()
  return {
    user: {
      id: me.id,
      email: me.email,
      is_superuser: me.is_superuser,
    },
    org,
    orgs: refreshed.length ? refreshed : [org],
  }
}

export const useAuthStore = create<AuthState>((set, get) => {
  setUnauthorizedHandler(() => {
    apiLogout()
    set({
      user: null,
      org: null,
      orgs: [],
      loginOpen: !get().demoMode && !get().setupOpen,
    })
  })

  return {
    ready: false,
    demoMode: isDemoMode(),
    user: null,
    org: null,
    orgs: [],
    loginOpen: false,
    setupOpen: false,
    setupStatus: null,
    pendingInvite: null,
    busy: false,
    error: null,

    bootstrap: async () => {
      const demoMode = isDemoMode()
      set({ demoMode })
      if (demoMode) {
        set({ ready: true, user: null, org: null, orgs: [], loginOpen: false, setupOpen: false })
        return
      }

      // Capture invite token from URL early
      try {
        const params = new URLSearchParams(window.location.search)
        const invite = params.get('invite')
        if (invite) set({ pendingInvite: invite })
      } catch {
        /* ignore */
      }

      let setupStatus: SetupStatus | null = null
      try {
        setupStatus = await getSetupStatus()
      } catch {
        setupStatus = null
      }

      if (setupStatus?.needs_setup) {
        set({
          ready: true,
          user: null,
          org: null,
          orgs: [],
          setupOpen: true,
          loginOpen: false,
          setupStatus,
        })
        return
      }

      const token = getAccessToken()
      if (!token) {
        set({
          ready: true,
          user: null,
          org: null,
          orgs: [],
          loginOpen: true,
          setupOpen: false,
          setupStatus,
        })
        return
      }
      try {
        const me = await getMe()
        const session = await loadSession(me.email)
        set({
          ready: true,
          ...session,
          loginOpen: false,
          setupOpen: false,
          setupStatus,
          error: null,
        })
        await get().consumePendingInvite()
      } catch {
        apiLogout()
        set({
          ready: true,
          user: null,
          org: null,
          orgs: [],
          loginOpen: true,
          setupOpen: false,
          setupStatus,
        })
      }
    },

    setLoginOpen: (v) => set({ loginOpen: v }),

    clearError: () => set({ error: null }),

    setPendingInvite: (token) => set({ pendingInvite: token }),

    consumePendingInvite: async () => {
      const token = get().pendingInvite
      if (!token || !get().user) return
      try {
        const result = await acceptInvite(token)
        setStoredOrgId(result.organization_id)
        const orgs = await listOrgs()
        const org = orgs.find((o) => o.id === result.organization_id) || orgs[0] || null
        set({ orgs, org, pendingInvite: null })
        try {
          const url = new URL(window.location.href)
          url.searchParams.delete('invite')
          window.history.replaceState({}, '', url.toString())
        } catch {
          /* ignore */
        }
      } catch {
        // Keep token so user can retry after fixing account mismatch
      }
    },

    completeSetup: async (payload) => {
      set({ busy: true, error: null })
      try {
        const result = await bootstrapSetup(payload)
        setAccessToken(result.access_token)
        setStoredOrgId(result.org_id)
        const session = await loadSession(result.email)
        set({
          ...session,
          setupOpen: false,
          loginOpen: false,
          busy: false,
          error: null,
          setupStatus: { ...(get().setupStatus || { environment: 'development', warnings: [], oauth: { github: false, google: false } }), needs_setup: false },
        })
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : 'Setup failed'
        set({ busy: false, error: msg })
        throw e
      }
    },

    login: async (email, password) => {
      set({ busy: true, error: null })
      try {
        await apiLogin(email.trim(), password)
        const session = await loadSession(email.trim())
        set({ ...session, loginOpen: false, busy: false, error: null })
        await get().consumePendingInvite()
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : 'Login failed'
        set({ busy: false, error: msg })
        throw e
      }
    },

    register: async (email, password) => {
      set({ busy: true, error: null })
      try {
        await apiRegister(email.trim(), password)
        await apiLogin(email.trim(), password)
        const session = await loadSession(email.trim())
        set({ ...session, loginOpen: false, busy: false, error: null })
        await get().consumePendingInvite()
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : 'Registration failed'
        set({ busy: false, error: msg })
        throw e
      }
    },

    refreshOrgs: async () => {
      const orgs = await listOrgs()
      const current = get().org
      const org =
        (current && orgs.find((o) => o.id === current.id)) || orgs[0] || null
      if (org) setStoredOrgId(org.id)
      set({ orgs, org })
    },

    switchOrg: async (orgId) => {
      const orgs = get().orgs.length ? get().orgs : await listOrgs()
      const org = orgs.find((o) => o.id === orgId)
      if (!org) return
      setStoredOrgId(org.id)
      set({ org, orgs })
    },

    logout: () => {
      apiLogout()
      set({
        user: null,
        org: null,
        orgs: [],
        loginOpen: !get().demoMode && !get().setupOpen,
        error: null,
      })
    },
  }
})
