import http from './http'

export interface User {
  id: number
  username: string
  email: string
  nickname: string
  avatar: string
  bio: string
  is_admin: boolean
  created_at: string
}

export interface TokenResp {
  access_token: string
  token_type: string
  user: User
}

export const authApi = {
  register(data: { username: string; email: string; password: string; nickname?: string }) {
    return http.post<unknown, TokenResp>('/auth/register', data)
  },
  login(data: { username: string; password: string }) {
    return http.post<unknown, TokenResp>('/auth/login', data)
  },
  me() {
    return http.get<unknown, User>('/auth/me')
  },
}
