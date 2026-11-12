import DOMPurify from 'dompurify'

const RICH_TEXT_TAG = /<\/?(?:p|div|h[1-6]|ul|ol|li|blockquote|pre|code|img|video|br|strong|b|em|i|u|s|a|hr|script|iframe|style)\b[^>]*>/i
const SAFE_IMAGE_URL = /^(https?:\/\/|\/(?!\/))/i
const SAFE_LINK_URL = /^(https?:\/\/|mailto:|\/(?!\/)|#)/i

function escapeText(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Normalize legacy text and rich text into the same safe display format. */
export function toArticleHtml(content: string): string {
  if (!content) return ''
  if (!RICH_TEXT_TAG.test(content)) {
    return content.replace(/\r\n?/g, '\n').split(/\n{2,}/)
      .map((paragraph) => `<p>${escapeText(paragraph).replace(/\n/g, '<br>')}</p>`).join('')
  }

  return sanitizeArticleHtml(content)
}

/** The clipboard already supplies HTML; do not apply legacy text detection. */
export function sanitizeArticleHtml(content: string): string {
  const clean = DOMPurify.sanitize(content, {
    ALLOWED_TAGS: ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
      'blockquote', 'pre', 'code', 'img', 'video', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'a', 'hr', 'span'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title', 'style', 'class', 'start', 'controls', 'preload', 'playsinline'],
    ALLOW_DATA_ATTR: false,
  })
  const template = document.createElement('template')
  template.innerHTML = clean
  template.content.querySelectorAll<HTMLElement>('[style]').forEach((element) => {
    const align = element.style.textAlign
    element.removeAttribute('style')
    if (['left', 'center', 'right', 'justify'].includes(align)) element.style.textAlign = align
  })
  template.content.querySelectorAll('a').forEach((link) => {
    if (!SAFE_LINK_URL.test(link.getAttribute('href') || '')) link.removeAttribute('href')
    link.setAttribute('target', '_blank')
    link.setAttribute('rel', 'noopener noreferrer')
  })
  template.content.querySelectorAll('img').forEach((image) => {
    if (!SAFE_IMAGE_URL.test(image.getAttribute('src') || '')) image.remove()
  })
  template.content.querySelectorAll('video').forEach((video) => {
    if (!SAFE_IMAGE_URL.test(video.getAttribute('src') || '')) { video.remove(); return }
    video.replaceChildren()
    video.setAttribute('controls', '')
    video.setAttribute('preload', 'metadata')
    video.setAttribute('playsinline', '')
  })
  return template.innerHTML
}

export function getArticleText(content: string): string {
  const template = document.createElement('template')
  template.innerHTML = toArticleHtml(content)
  template.content.querySelectorAll('br').forEach((br) => br.replaceWith('\n'))
  template.content.querySelectorAll('p, div, h1, h2, h3, h4, h5, h6, li, blockquote, pre')
    .forEach((block) => block.append('\n'))
  return (template.content.textContent || '').replace(/[\u200b-\u200d\ufeff]/g, '')
    .replace(/\n{3,}/g, '\n\n').trim()
}

export function hasArticleContent(content: string): boolean {
  if (getArticleText(content).trim()) return true
  const template = document.createElement('template')
  template.innerHTML = toArticleHtml(content)
  return Boolean(template.content.querySelector('img[src], video[src]'))
}
