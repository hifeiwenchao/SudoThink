export interface ContactFields {
  github_url?: string
  email?: string
  x_url?: string
  facebook_url?: string
  instagram_url?: string
}

export const contactFields = [
  { key: 'github_url', label: 'GitHub', placeholder: 'https://github.com/your-name' },
  { key: 'email', label: '邮箱', placeholder: 'hello@example.com' },
  { key: 'x_url', label: 'X', placeholder: 'https://x.com/your-name' },
  { key: 'facebook_url', label: 'Facebook', placeholder: 'https://www.facebook.com/your-name' },
  { key: 'instagram_url', label: 'Instagram', placeholder: 'https://www.instagram.com/your-name' },
] as const

export function isContactUrl(value: string): boolean {
  if (value.length > 512 || /[\s\p{Cc}\p{Cf}\\]/u.test(value) || !/^https?:\/\//i.test(value)) return false
  try {
    const url = new URL(value)
    return Boolean(url.hostname) && !url.username && !url.password
  } catch {
    return false
  }
}

export function isContactEmail(value: string): boolean {
  return value.length <= 254 && /^[a-zA-Z0-9.!$'*+\/_`{|}~^-]+@[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,}$/.test(value)
}
