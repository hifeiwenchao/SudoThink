import axios, { type AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

export const http: AxiosInstance = axios.create({
  baseURL,
  timeout: 15000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
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
    const status = error?.response?.status
    const msg =
      error?.response?.data?.message ||
      error?.message ||
      '网络错误'
    if (status === 401) {
      localStorage.removeItem('access_token')
      ElMessage.error('登录已失效，请重新登录')
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default http
