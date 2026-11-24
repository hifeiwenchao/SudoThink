import axios, { type AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'
import { readSession, expireSession } from '@/utils/session'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 15000,
})

http.interceptors.request.use((config) => {
  const token = readSession().token
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(body)
    }
    return body
  },
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    const status = error?.response?.status
    const msg =
      error?.response?.data?.message ||
      error?.message ||
      '网络错误'
    if (status === 401 && !/\/auth\/(login|register)(?:\?|$)/.test(error?.config?.url || '')) {
      const authorization = String(error?.config?.headers?.Authorization || '')
      if (expireSession(authorization.replace(/^Bearer /, ''))) {
        ElMessage.error('登录已失效，请重新登录')
        if (window.location.pathname !== '/login') {
          const redirect = window.location.pathname + window.location.search + window.location.hash
          window.location.replace(`/login?redirect=${encodeURIComponent(redirect)}`)
        }
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default http
