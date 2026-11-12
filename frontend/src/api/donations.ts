import axios from 'axios'
import http from './http'

export interface DonationSettingsInput {
  enabled: boolean
  wechat_qr_url: string
  alipay_qr_url: string
}

export interface DonationSettings extends DonationSettingsInput {
  updated_at?: string | null
}

export const donationsApi = {
  async get(signal?: AbortSignal) {
    const response = await axios.get<{ code: number; data: DonationSettings; message?: string }>('/donations', {
      baseURL: http.defaults.baseURL,
      timeout: http.defaults.timeout,
      signal,
    })
    if (response.data?.code !== 0) throw new Error(response.data?.message || '打赏设置加载失败')
    return response.data.data
  },
  adminGet(signal?: AbortSignal) {
    return http.get<unknown, DonationSettings>('/admin/donations', { signal })
  },
  save(data: DonationSettingsInput, signal?: AbortSignal) {
    return http.put<unknown, DonationSettings>('/admin/donations', data, { signal })
  },
}
