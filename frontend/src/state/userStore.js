import { create } from 'zustand'
import { api, getStoredToken, setStoredToken, clearStoredToken, setUnauthorizedHandler } from '../lib/api'

export const useUserStore = create((set, get) => ({
  user: null, // { id, name, role }
  status: 'idle', // idle | loading | ready
  error: null,

  async init() {
    const token = getStoredToken()
    if (!token) {
      set({ status: 'ready', user: null })
      return
    }
    set({ status: 'loading' })
    try {
      const user = await api.get('/me')
      set({ user, status: 'ready', error: null })
    } catch (err) {
      clearStoredToken()
      set({ status: 'ready', user: null, error: err.message })
    }
  },

  // Combined login-or-register, matching the backend: a name that doesn't
  // exist yet creates an account, one that does gets a real password check.
  async authenticate(name, password) {
    set({ status: 'loading', error: null })
    try {
      const { token, user } = await api.post('/auth/authenticate', { name, password })
      setStoredToken(token)
      set({ user, status: 'ready' })
    } catch (err) {
      set({ status: 'ready', user: null, error: err.message })
      throw err
    }
  },

  async logout() {
    try {
      await api.post('/auth/logout', {})
    } catch {
      // even if the request fails, still clear the local session below
    }
    clearStoredToken()
    set({ user: null })
  },
}))

// wired once, outside the store body, so a 401 from anywhere drops back to
// the login screen without every page needing to know about it
setUnauthorizedHandler(() => {
  useUserStore.setState({ user: null, status: 'ready' })
})
