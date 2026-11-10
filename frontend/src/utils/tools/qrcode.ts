import QRCode from 'qrcode'
import jsQR from 'jsqr'

const MAX_CONTENT_BYTES = 2000
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_IMAGE_PIXELS = 16_000_000

export function createQrMatrix(text: string): { size: number; data: Uint8Array } {
  if (!text.trim()) throw new Error('请输入需要生成二维码的内容。')
  if (new TextEncoder().encode(text).length > MAX_CONTENT_BYTES) {
    throw new Error(`内容过长，请控制在 ${MAX_CONTENT_BYTES} 个 UTF-8 字节以内。`)
  }
  try {
    const { modules } = QRCode.create(text, { errorCorrectionLevel: 'M' })
    return { size: modules.size, data: modules.data }
  } catch {
    throw new Error('内容超过二维码容量，请缩短后重试。')
  }
}

export function createQrPng(text: string): string {
  const matrix = createQrMatrix(text)
  const scale = 6
  const margin = 4
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = (matrix.size + margin * 2) * scale
  const context = canvas.getContext('2d')
  if (!context) throw new Error('当前浏览器无法生成图片，请换用支持 Canvas 的浏览器。')
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = '#000000'
  for (let y = 0; y < matrix.size; y++) {
    for (let x = 0; x < matrix.size; x++) {
      if (matrix.data[y * matrix.size + x]) {
        context.fillRect((x + margin) * scale, (y + margin) * scale, scale, scale)
      }
    }
  }
  return canvas.toDataURL('image/png')
}

export function validateQrFile(file: { type: string; size: number }): void {
  if (!file.type.startsWith('image/')) throw new Error('请选择图片文件，例如 PNG、JPEG 或 WebP。')
  if (file.size > MAX_IMAGE_BYTES) throw new Error('图片不能超过 10 MB，请压缩后重试。')
  if (file.size <= 0) throw new Error('图片文件为空，请重新选择。')
}

export function validateQrDimensions(width: number, height: number): void {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new Error('无法读取有效的图片尺寸。')
  }
  if (width * height > MAX_IMAGE_PIXELS) throw new Error('图片像素不能超过 1600 万，请缩小后重试。')
}

export function decodeQrPixels(pixels: Uint8ClampedArray, width: number, height: number): string {
  validateQrDimensions(width, height)
  if (pixels.length !== width * height * 4) throw new Error('图片像素数据不完整，请重新选择。')
  const result = jsQR(pixels, width, height, { inversionAttempts: 'attemptBoth' })
  if (!result) throw new Error('未识别到二维码，请选择清晰、完整且留有边缘的二维码图片。')
  return result.data
}

export async function readQrImage(file: File): Promise<string> {
  validateQrFile(file)
  const source = URL.createObjectURL(file)
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const candidate = new Image()
      candidate.onload = () => resolve(candidate)
      candidate.onerror = () => reject(new Error('图片读取失败，文件可能损坏或格式不受浏览器支持。'))
      candidate.src = source
    })
    validateQrDimensions(image.naturalWidth, image.naturalHeight)
    const canvas = document.createElement('canvas')
    canvas.width = image.naturalWidth
    canvas.height = image.naturalHeight
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) throw new Error('当前浏览器无法读取图片，请换用支持 Canvas 的浏览器。')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0)
    return decodeQrPixels(context.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height)
  } finally {
    URL.revokeObjectURL(source)
  }
}
