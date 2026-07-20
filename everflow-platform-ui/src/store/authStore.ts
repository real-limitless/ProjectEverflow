import { create } from 'zustand'
import {
  ApiError,
  ensureOrg,
  getAccessToken,
  getMe,
  isDemoMode,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  setUnauthorizedHandler,
  type Org,
} from '@/lib/api'

export type AuthUser = { id: string; email: string }

interface AuthState {
  ready: boolean
  demoMode: boolean
  user: AuthUser | null
  org: Org | null
  loginOpen: boolean
  busy: boolean
  error: string | null

  bootstrap: () => Promise<void>
  setLoginOpen: (v: boolean) => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  clearError: () => void
}

export const useAuthStore = create<AuthState>((set, get) => {
  setUnauthorizedHandler(() => {
    apiLogout()
    set({ user: null, org: null, loginOpen: !get().demoMode })
  })

  return {
    ready: false,
    demoMode: isDemoMode(),
    user: null,
    org: null,
    loginOpen: false,
    busy: false,
    error: null,

    bootstrap: async () => {
      const demoMode = isDemoMode()
      set({ demoMode })
      if (demoMode) {
        set({ ready: true, user: null, org: null, loginOpen: false })
        return
      }
      const token = getAccessToken()
      if (!token) {
        set({ ready: true, user: null, org: null, loginOpen: true })
        return
      }
      try {
        const me = await getMe()
        const org = await ensureOrg(me.email)
        set({ ready: true, user: me, org, loginOpen: false, error: null })
      } catch {
        apiLogout()
        set({ ready: true, user: null, org: null, loginOpen: true })
      }
    },

    setLoginOpen: (v) => set({ loginOpen: v }),

    clearError: () => set({ error: null }),

    login: async (email, password) => {
      set({ busy: true, error: null })
      try {
        await apiLogin(email.trim(), password)
        const me = await getMe()
        const org = await ensureOrg(me.email)
        set({ user: me, org, loginOpen: false, busy: false, error: null })
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
        const me = await getMe()
        const org = await ensureOrg(me.email)
        set({ user: me, org, loginOpen: false, busy: false, error: null })
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : 'Registration failed'
        set({ busy: false, error: msg })
        throw e
      }
    },

    logout: () => {
      apiLogout()
      set({
        user: null,
        org: null,
        loginOpen: !get().demoMode,
        error: null,
      })
    },
  }
})
