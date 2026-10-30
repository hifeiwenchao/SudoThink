import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type User } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const user = ref<User | null>(
    JSON.parse(localStorage.getItem('user') || 'null'),
  )

  const isLoggedIn = computed(() => !!token.value)

  function setSession(t: string, u: User) {
    token.value = t
    user.value = u
    localStorage.setItem('access_token', t)
    localStorage.setItem('user', JSON.stringify(u))
  }

  async function login(username: string, password: string) {
    const data = await authApi.login({ username, password })
    setSession(data.access_token, data.user)
  }

  async function register(payload: {
    username: string
    email: string
    password: string
    nickname?: string
  }) {
    const data = await authApi.register(payload)
    setSession(data.access_token, data.user)
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
  }

  return { token, user, isLoggedIn, login, register, logout }
})
