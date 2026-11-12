import type { CdnConfiguration, CdnOperation } from '../api/operations'

export function parseCdnUrls(input: string): string[] {
  return [...new Set(input.split(/\r?\n/).map((line) => line.trim()).filter(Boolean))]
}

export function cdnOperationLimit(operation: CdnOperation, limits: CdnConfiguration['limits']): number {
  const fields = { File: 'refresh_file', Directory: 'refresh_directory', Regex: 'refresh_regex', Preload: 'preload' } as const
  return limits[fields[operation]]
}

export function validateCdnUrls(urls: string[], operation: CdnOperation, limits: CdnConfiguration['limits']): string {
  if (!urls.length) return '请至少输入一条完整的 HTTP/HTTPS 地址。'
  const limit = cdnOperationLimit(operation, limits)
  if (urls.length > limit) return `本次最多提交 ${limit} 条地址，当前为 ${urls.length} 条。`
  const hosts = new Set<string>()
  for (const [index, value] of urls.entries()) {
    const label = `第 ${index + 1} 条地址`
    if (value.length > limits.max_url_length) return `${label}超过 ${limits.max_url_length} 字符。`
    try {
      const url = new URL(value)
      if (!/^https?:\/\//i.test(value) || !url.hostname || url.username || url.password || value.includes('#') || /[\s\u0000-\u001f\u007f]/.test(value) || (operation !== 'Regex' && value.includes('\\'))) {
        return `${label}必须为完整的 HTTP/HTTPS 地址，不能含账号密码、空白或片段（#）。`
      }
      const authority = value.match(/^https?:\/\/([^/?#]+)/i)?.[1] ?? ''
      if (authority.includes(':') || authority.length > 253 || !authority.split('.').every((part) => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i.test(part)) || /^(?:\d{1,3}\.){3}\d{1,3}$/.test(url.hostname)) {
        return `${label}请使用有效的 CDN 加速域名，不能含端口或 IP 地址。`
      }
      hosts.add(url.hostname.toLowerCase())
      if (operation === 'Directory' && (!url.pathname.endsWith('/') || value.includes('?'))) return `${label}是目录地址，请以 / 结尾且不要带查询参数。`
      if (operation === 'Preload' && url.pathname.endsWith('/')) return `${label}是目录地址，URL 预热仅支持文件地址。`
      if (operation === 'Regex') {
        let pattern = value.slice(value.indexOf(authority) + authority.length)
        for (const supported of ['[0-9]', '[a-z]', '[^/]*', '.*']) pattern = pattern.replaceAll(supported, '')
        if (/[\[\]*\\{}()|^$]/.test(pattern)) return `${label}的正则刷新仅支持 [0-9]、[a-z]、[^/]* 和 .* 模式。`
      }
    } catch {
      return `${label}格式不正确，请输入完整的 HTTP/HTTPS 地址。`
    }
  }
  if (hosts.size > 10) return '每次最多提交 10 个 CDN 域名，请分批操作。'
  return ''
}
