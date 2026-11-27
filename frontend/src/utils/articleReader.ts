/** Adds controls to the rendered, sanitized article only; never changes stored HTML. */
export function enhanceArticle(root: HTMLElement, preview: (image: HTMLImageElement) => void) {
  let disposed = false
  const timers = new Set<ReturnType<typeof setTimeout>>()
  const buttons = new Map<HTMLButtonElement, { text: string; version: number }>()
  const images = new Set<HTMLImageElement>()
  for (const pre of root.querySelectorAll('pre')) {
    // Read before adding controls so labels can never enter the clipboard text.
    const text = pre.querySelector('code')?.textContent ?? pre.textContent ?? ''
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'article-code-copy'
    button.textContent = '复制代码'
    button.setAttribute('aria-live', 'polite')
    pre.prepend(button)
    buttons.set(button, { text, version: 0 })
  }
  for (const image of root.querySelectorAll('img')) {
    if (image.closest('a') || !/^(https?:\/\/|\/(?!\/))/i.test(image.getAttribute('src') || '')) continue
    image.tabIndex = 0
    image.setAttribute('role', 'button')
    image.setAttribute('aria-label', `放大图片：${image.alt || '文章图片'}`)
    image.classList.add('article-preview-image')
    images.add(image)
  }
  async function copy(button: HTMLButtonElement) {
    const state = buttons.get(button)!
    const version = ++state.version
    try {
      if (navigator.clipboard?.writeText) {
        try { await navigator.clipboard.writeText(state.text) }
        catch { if (!disposed && version === state.version) fallbackCopy(state.text) }
      } else fallbackCopy(state.text)
      if (disposed || version !== state.version) return
      button.textContent = '已复制'
    } catch {
      if (disposed || version !== state.version) return
      button.textContent = '复制失败，请手动复制'
    }
    const timer = setTimeout(() => {
      timers.delete(timer)
      if (!disposed && version === state.version) button.textContent = '复制代码'
    }, 2000)
    timers.add(timer)
  }
  function onClick(event: MouseEvent) {
    const target = event.target
    if (!(target instanceof Element)) return
    const button = target.closest('button') as HTMLButtonElement | null
    if (button && buttons.has(button)) { void copy(button); return }
    if (images.has(target as HTMLImageElement) && event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) preview(target as HTMLImageElement)
  }
  function onKeydown(event: KeyboardEvent) {
    if ((event.key === 'Enter' || event.key === ' ') && images.has(event.target as HTMLImageElement)) {
      event.preventDefault()
      preview(event.target as HTMLImageElement)
    }
  }
  root.addEventListener('click', onClick)
  root.addEventListener('keydown', onKeydown)
  return () => {
    disposed = true
    timers.forEach(clearTimeout)
    root.removeEventListener('click', onClick)
    root.removeEventListener('keydown', onKeydown)
    buttons.forEach((_, button) => button.remove())
    images.forEach((image) => {
      image.removeAttribute('tabindex'); image.removeAttribute('role'); image.removeAttribute('aria-label')
      image.classList.remove('article-preview-image')
    })
  }
}

// Same focus-preserving fallback used by the local tools' CopyButton.
function fallbackCopy(text: string) {
  const focused = document.activeElement as HTMLElement | null
  const input = document.createElement('textarea')
  input.value = text
  input.readOnly = true
  input.tabIndex = -1
  input.setAttribute('aria-hidden', 'true')
  Object.assign(input.style, { position: 'fixed', left: '-9999px', top: '0' })
  document.body.append(input)
  try {
    input.focus(); input.select()
    if (!document.execCommand('copy')) throw new Error('Copy unavailable')
  } finally {
    input.remove()
    focused?.focus({ preventScroll: true })
  }
}
