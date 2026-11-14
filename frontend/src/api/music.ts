import axios from 'axios'
import http from './http'

export interface MusicTrack {
  title: string
  artist: string
  url: string
}

export interface MusicSettingsInput {
  enabled: boolean
  tracks: MusicTrack[]
}

export interface MusicSettings extends MusicSettingsInput {
  updated_at?: string | null
}

export const musicApi = {
  async get(signal?: AbortSignal) {
    const response = await axios.get<{ code: number; data: MusicSettings; message?: string }>('/music', {
      baseURL: http.defaults.baseURL,
      timeout: http.defaults.timeout,
      signal,
    })
    if (response.data?.code !== 0) throw new Error(response.data?.message || '音乐设置加载失败')
    return response.data.data
  },
  adminGet(signal?: AbortSignal) {
    return http.get<unknown, MusicSettings>('/admin/music', { signal })
  },
  save(input: MusicSettingsInput) {
    return http.put<unknown, MusicSettings>('/admin/music', input)
  },
}
