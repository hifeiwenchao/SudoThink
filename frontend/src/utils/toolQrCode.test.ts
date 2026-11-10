import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  createQrMatrix,
  decodeQrPixels,
  validateQrFile,
  validateQrDimensions,
} from './tools/qrcode'

describe('QR code tools', () => {
  it('generates a QR matrix that decodes Chinese, emoji and URL punctuation unchanged', () => {
    const content = '你好，SudoThink 🌍\nhttps://example.com/?a=1&b=中文'
    const matrix = createQrMatrix(content)
    const scale = 5
    const quiet = 4
    const size = (matrix.size + quiet * 2) * scale
    const pixels = new Uint8ClampedArray(size * size * 4).fill(255)
    for (let y = 0; y < matrix.size; y++) {
      for (let x = 0; x < matrix.size; x++) {
        if (!matrix.data[y * matrix.size + x]) continue
        for (let dy = 0; dy < scale; dy++) {
          for (let dx = 0; dx < scale; dx++) {
            const offset = (((y + quiet) * scale + dy) * size + (x + quiet) * scale + dx) * 4
            pixels[offset] = pixels[offset + 1] = pixels[offset + 2] = 0
          }
        }
      }
    }
    assert.equal(decodeQrPixels(pixels, size, size), content)
  })

  it('rejects empty or excessive content before generating a matrix', () => {
    assert.throws(() => createQrMatrix(' \n\t'), /内容/)
    assert.throws(() => createQrMatrix('中'.repeat(1000)), /容量|字节|过长/)
  })

  it('reports an image without a QR code instead of returning stale text', () => {
    assert.throws(() => decodeQrPixels(new Uint8ClampedArray(200 * 200 * 4).fill(255), 200, 200), /未.*二维码/)
  })

  it('rejects non-images, oversized files and excessive decoded dimensions', () => {
    assert.throws(() => validateQrFile({ type: 'text/plain', size: 20 }), /图片/)
    assert.throws(() => validateQrFile({ type: 'image/png', size: 11 * 1024 * 1024 }), /10 MB/)
    assert.doesNotThrow(() => validateQrFile({ type: 'image/png', size: 1024 }))
    assert.throws(() => validateQrDimensions(5000, 5000), /像素/)
    assert.throws(() => validateQrDimensions(0, 500), /尺寸/)
    assert.throws(() => decodeQrPixels(new Uint8ClampedArray(4), 100, 100), /像素/)
  })
})
