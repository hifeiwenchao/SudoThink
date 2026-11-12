import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, it } from 'node:test'
import { uploadMedia, validateMediaFile, type UploadConfig, type UploadPolicy } from './mediaUpload'

const config: UploadConfig = {
  enabled: true,
  image_max_bytes: 10,
  video_max_bytes: 20,
  image_types: { 'image/jpeg': ['.jpg', '.jpeg'], 'image/png': ['.png'] },
  video_types: { 'video/mp4': ['.mp4'], 'video/webm': ['.webm'] },
}
const policy: UploadPolicy = {
  upload_url: 'https://bucket.oss-cn-hangzhou.aliyuncs.com',
  public_url: 'https://cdn.example.com/media/images/unique.png',
  key: 'media/images/unique.png',
  fields: {
    key: 'media/images/unique.png', policy: 'signed-policy',
    'x-oss-signature-version': 'OSS4-HMAC-SHA256', 'x-oss-signature': 'signed',
    'Content-Type': 'image/png', 'x-oss-content-type': 'image/png', success_action_status: '201',
  },
  expires_at: '2026-11-12T09:05:00Z',
}

// Only the external OSS transport is replaced; FormData and the upload pipeline stay real.
class OssRequest {
  static respond: (request: OssRequest) => void = () => {}
  method = ''
  url = ''
  body: FormData | undefined
  headers: Record<string, string> = {}
  withCredentials = false
  status = 0
  responseText = ''
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  ontimeout: (() => void) | null = null
  open(method: string, url: string) { this.method = method; this.url = url }
  setRequestHeader(name: string, value: string) { this.headers[name] = value }
  send(body: FormData) { this.body = body; queueMicrotask(() => OssRequest.respond(this)) }
  abort() { this.onabort?.() }
  complete(status: number, response = '') { this.status = status; this.responseText = response; this.onload?.() }
}
const originalXHR = globalThis.XMLHttpRequest
beforeEach(() => { Object.assign(globalThis, { XMLHttpRequest: OssRequest }) })
afterEach(() => { Object.assign(globalThis, { XMLHttpRequest: originalXHR }) })

describe('media validation', () => {
  it('accepts configured MIME and case-insensitive matching extension', () => {
    assert.deepEqual(validateMediaFile(new File(['png'], 'photo.PNG', { type: 'image/png' }), config), { kind: 'image', contentType: 'image/png' })
    assert.equal(validateMediaFile(new File(['clip'], 'clip.mp4', { type: 'video/mp4' }), config).kind, 'video')
  })

  for (const [file, reason] of [
    [new File(['x'], 'photo.svg', { type: 'image/svg+xml' }), /支持/],
    [new File(['x'], 'photo.jpg', { type: 'image/png' }), /后缀/],
    [new File(['x'], 'photo.png', { type: '' }), /支持/],
    [new File([], 'empty.png', { type: 'image/png' }), /空文件/],
    [new File(['01234567890'], 'large.png', { type: 'image/png' }), /过大/],
    [new File(['012345678901234567890'], 'large.mp4', { type: 'video/mp4' }), /过大/],
  ] as const) {
    it(`rejects an unsupported, mismatched, empty, or oversized file: ${file.name}/${file.type}`, async () => {
      await assert.rejects(uploadMedia(file, {
        config,
        requestPolicy: async () => { assert.fail('invalid files must not request upload credentials') },
      }), reason)
    })
  }

  it('rejects uploads when disabled and video files used as covers', () => {
    const image = new File(['x'], 'photo.png', { type: 'image/png' })
    const video = new File(['x'], 'clip.mp4', { type: 'video/mp4' })
    assert.throws(() => validateMediaFile(image, { ...config, enabled: false }), /未启用/)
    assert.throws(() => validateMediaFile(video, config, 'image'), /图片/)
  })
})

describe('OSS direct uploads', () => {
  for (const [status, response] of [[200, ''], [201, '<PostResponse><Key>media/images/unique.png</Key></PostResponse>']] as const) {
    it(`submits signed fields before the file and accepts OSS ${status} without JSON parsing`, async () => {
      const file = new File(['png'], 'photo.png', { type: 'image/png' })
      const progress: number[] = []
      OssRequest.respond = (request) => {
        assert.equal(request.method, 'POST')
        assert.equal(request.url, 'https://bucket.oss-cn-hangzhou.aliyuncs.com')
        assert.equal(request.withCredentials, false)
        assert.deepEqual(request.headers, {})
        const entries = [...request.body!.entries()]
        assert.deepEqual(entries.slice(0, -1), Object.entries(policy.fields))
        assert.equal(entries.at(-1)?.[0], 'file')
        assert.equal((entries.at(-1)?.[1] as File).name, 'photo.png')
        request.upload.onprogress?.({ lengthComputable: true, loaded: 3, total: 6 } as ProgressEvent)
        request.complete(status, response)
      }
      const result = await uploadMedia(file, {
        config,
        onProgress: (value) => progress.push(value),
        requestPolicy: async (input) => {
          assert.deepEqual(input, { filename: 'photo.png', size: 3, content_type: 'image/png' })
          return policy
        },
      })
      assert.deepEqual(result, { url: 'https://cdn.example.com/media/images/unique.png', key: 'media/images/unique.png', kind: 'image' })
      assert.ok(progress.includes(50))
      assert.equal(progress.at(-1), 100)
    })
  }

  it('rejects failed OSS responses without reporting a public URL', async () => {
    OssRequest.respond = (request) => request.complete(403, '<Error><Code>AccessDenied</Code></Error>')
    await assert.rejects(uploadMedia(new File(['x'], 'photo.png', { type: 'image/png' }), {
      config, requestPolicy: async () => policy,
    }), /403/)
  })

  it('rejects network failures', async () => {
    OssRequest.respond = (request) => request.onerror?.()
    await assert.rejects(uploadMedia(new File(['x'], 'photo.png', { type: 'image/png' }), {
      config, requestPolicy: async () => policy,
    }), Error)
  })

  it('does not request a policy for an already cancelled upload', async () => {
    const controller = new AbortController()
    controller.abort()
    await assert.rejects(uploadMedia(new File(['x'], 'photo.png', { type: 'image/png' }), {
      config, signal: controller.signal,
      requestPolicy: async () => { assert.fail('cancelled upload must not request credentials') },
    }), { name: 'AbortError' })
  })

  it('forwards cancellation to the policy request and never starts OSS afterwards', async () => {
    const controller = new AbortController()
    OssRequest.respond = () => { assert.fail('cancelled signature must not start OSS') }
    const task = uploadMedia(new File(['x'], 'photo.png', { type: 'image/png' }), {
      config, signal: controller.signal,
      requestPolicy: async (_input, signal) => {
        assert.equal(signal, controller.signal)
        await new Promise<void>((resolve) => signal?.addEventListener('abort', () => resolve(), { once: true }))
        return policy
      },
    })
    controller.abort()
    await assert.rejects(task, { name: 'AbortError' })
  })

  it('aborts the OSS request and ignores a late successful response', async () => {
    const controller = new AbortController()
    OssRequest.respond = (request) => {
      controller.abort()
      request.complete(201, '<PostResponse/>')
    }
    await assert.rejects(uploadMedia(new File(['x'], 'photo.png', { type: 'image/png' }), {
      config, signal: controller.signal, requestPolicy: async () => policy,
    }), { name: 'AbortError' })
  })
})
