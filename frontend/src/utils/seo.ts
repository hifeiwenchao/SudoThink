import { PUBLIC_SITE_URL } from '../site'
export interface PageSeo { title: string; description: string; path: string; image?: string; type?: 'website' | 'article'; noindex?: boolean }
const description = 'SudoThink：分享技术探索、实践经验与日常思考。保持好奇，认真思考，持续记录。'
export function routeSeo(path: string, admin = false): PageSeo {
  const page = path === '/about' ? ['关于我', '关于 SudoThink 与博客作者，记录技术、生活与探索。'] : path === '/tools' ? ['工具箱', '时间戳、二维码、JSON、cron 等浏览器本地实用工具。'] : path === '/' ? ['记录、思考，然后构建', description] : path.startsWith('/articles/') && /^\/articles\/\d+$/.test(path) ? ['文章', description] : ['页面未找到', '页面可能已移动或不存在，欢迎浏览 SudoThink 的其他文章。']
  return { title: page[0]!, description: page[1]!, path, noindex: admin || path === '/login' || path.startsWith('/admin') || path.endsWith('/edit') || path === '/articles/new' || page[0] === '页面未找到' }
}
export function setPageSeo(seo: PageSeo, doc: Document = document) {
  doc.title = `${seo.title} | SudoThink`
  function meta(key: string, content: string, property = false) {
    const attr = property ? 'property' : 'name'
    const nodes = [...doc.head.querySelectorAll<HTMLMetaElement>(`meta[${attr}="${key}"]`)]
    const node = nodes.shift() || doc.createElement('meta')
    nodes.forEach((item) => item.remove())
    node.setAttribute(attr, key)
    node.content = content
    doc.head.append(node)
  }
  const canonical = new URL(seo.path, PUBLIC_SITE_URL).href
  const links = [...doc.head.querySelectorAll<HTMLLinkElement>('link[rel="canonical"]')]
  const link = links.shift() || doc.createElement('link')
  links.forEach((item) => item.remove())
  link.rel = 'canonical'; link.href = canonical; doc.head.append(link)
  meta('description', seo.description)
  meta('robots', seo.noindex ? 'noindex, nofollow' : 'index, follow')
  meta('og:title', doc.title, true); meta('og:description', seo.description, true)
  meta('og:url', canonical, true); meta('og:type', seo.type || 'website', true)
  meta('og:site_name', 'SudoThink', true)
  doc.head.querySelectorAll('meta[property="og:image"]').forEach((item) => item.remove())
  if (seo.image) {
    try {
      const image = new URL(seo.image, PUBLIC_SITE_URL)
      if (['http:', 'https:'].includes(image.protocol)) meta('og:image', image.href, true)
    } catch { /* An invalid cover should not prevent navigation. */ }
  }
}
