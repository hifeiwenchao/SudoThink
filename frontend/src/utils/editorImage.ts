import Image from '@tiptap/extension-image'

function dimension(value: unknown): number | null {
  if (typeof value !== 'string' && typeof value !== 'number') return null
  if (!/^[1-9]\d{0,4}$/.test(String(value))) return null
  const number = Number(value)
  return number <= 10000 ? number : null
}

export const ArticleImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      ...Object.fromEntries(['width', 'height'].map(name => [name, {
        default: null,
        parseHTML: (element: HTMLElement) => dimension(element.getAttribute(name)),
        renderHTML: (attributes: Record<string, unknown>) => {
          const value = dimension(attributes[name])
          return value ? { [name]: value } : {}
        },
      }])),
    }
  },
}).configure({ allowBase64: false })

/** Decode only a local upload; remote images need no extra network request. */
export async function imageDimensions(blob: Blob): Promise<{ width?: number; height?: number }> {
  if (typeof createImageBitmap !== 'function') return {}
  try {
    const bitmap = await createImageBitmap(blob)
    try {
      const width = dimension(bitmap.width), height = dimension(bitmap.height)
      return width && height ? { width, height } : {}
    } finally { bitmap.close() }
  } catch { return {} }
}
