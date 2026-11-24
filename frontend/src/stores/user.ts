import { defineStore } from 'pinia'
import { ref, computed, onScopeDispose } from 'vue'
import { authApi, type User } from '@/api/auth'
import { readSession, setSession, onSessionChange } from '@/utils/session'

export const useUserStore = defineStore('user', () => {
  const initial = readSession()
  const token = ref(initial.token)
  const user = ref<User | null>(initial.user)
  const stopSessionListener = onSessionChange((session) => {
    token.value = session.token
    user.value = session.user
  })
  onScopeDispose(stopSessionListener)
  const isLoggedIn = computed(() => !!token.value)
  async function login(username: string, password: string) {
    const data = await authApi.login({ username, password })
    setSession(data.access_token, data.user)
  }
  async function register(payload: { username: string; email: string; password: string; nickname?: string }) {
    const data = await authApi.register(payload)
    setSession(data.access_token, data.user)
  }
  function logout() { setSession('', null) }
  return { token, user, isLoggedIn, login, register, logout }
})
