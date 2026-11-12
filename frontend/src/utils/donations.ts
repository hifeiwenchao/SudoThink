export interface DonationConfiguration {
  enabled: boolean
  wechat_qr_url: string
  alipay_qr_url: string
}

export interface DonationChannel {
  key: 'wechat' | 'alipay'
  label: string
  url: string
}

export function isDonationQrUrl(value: string): boolean {
  if (!value || value.length > 2048 || /[\s\p{Cc}\p{Cf}\\#]/u.test(value)) return false
  try {
    const url = new URL(value)
    return /^https?:\/\//i.test(value) && ['http:', 'https:'].includes(url.protocol)
      && !!url.hostname && !url.username && !url.password
  } catch {
    return false
  }
}

export function getDonationChannels(settings: DonationConfiguration | null): DonationChannel[] {
  if (!settings?.enabled) return []
  const channels: DonationChannel[] = [
    { key: 'wechat', label: '微信', url: settings.wechat_qr_url.trim() },
    { key: 'alipay', label: '支付宝', url: settings.alipay_qr_url.trim() },
  ]
  return channels.filter(channel => isDonationQrUrl(channel.url))
}
