import http from './http'

export interface WechatSignature {
  app_id: string
  timestamp: number
  nonce_str: string
  signature: string
}

export const wechatApi = {
  signature(url: string) {
    return http.get<unknown, WechatSignature>('/wechat/signature', { params: { url } })
  },
}
