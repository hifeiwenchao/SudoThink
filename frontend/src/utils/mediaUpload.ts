export type UploadKind = 'image' | 'video' | 'audio'

export interface UploadConfig {
  enabled: boolean
  image_max_bytes: number
  video_max_bytes: number
  audio_max_bytes: number
  image_types: Record<string, string[]>
  video_types: Record<string, string[]>
  audio_types: Record<string, string[]>
}

export interface UploadPolicyInput {
  filename: string
  size: number
  content_type: string
}

export interface UploadPolicy {
  upload_url: string
  public_url: string
  key: string
  fields: Record<string, string>
  expires_at: string
}

export interface UploadedMedia {
  url: string
  key: string
  kind: UploadKind
}

interface UploadOptions {
  config: UploadConfig
  kind?: UploadKind
  signal?: AbortSignal
  onProgress?: (percentage: number) => void
  requestPolicy: (input: UploadPolicyInput, signal?: AbortSignal) => Promise<UploadPolicy>
}

export function validateMediaFile(file: File, config: UploadConfig, expectedKind?: UploadKind): { kind: UploadKind; contentType: string } {
  if (!config.enabled) throw new Error('暂未启用本地上传，可继续使用资源地址')
  let contentType = file.type.toLowerCase()
  const audioAliases: Record<string, string> = {
    'audio/mp3': 'audio/mpeg', 'audio/x-mp3': 'audio/mpeg', 'audio/x-mpeg': 'audio/mpeg',
    'audio/x-m4a': 'audio/mp4', 'audio/m4a': 'audio/mp4',
    'audio/x-wav': 'audio/wav', 'audio/wave': 'audio/wav', 'audio/vnd.wave': 'audio/wav',
    'application/ogg': 'audio/ogg', 'audio/x-ogg': 'audio/ogg',
  }
  contentType = audioAliases[contentType] ?? contentType
  if (expectedKind === 'audio' && (!contentType || contentType === 'application/octet-stream')) {
    contentType = Object.entries(config.audio_types).find(([, extensions]) =>
      extensions.some(extension => file.name.toLowerCase().endsWith(extension)))?.[0] ?? contentType
  }
  const kind = Object.hasOwn(config.image_types, contentType) ? 'image'
    : Object.hasOwn(config.video_types, contentType) ? 'video'
    : Object.hasOwn(config.audio_types, contentType) ? 'audio' : null
  if (!kind || (expectedKind && kind !== expectedKind)) throw new Error(expectedKind === 'image' ? '请选择支持的图片文件' : expectedKind === 'audio' ? '请选择支持的音频文件' : '请选择支持的图片或视频文件')
  const extensions = kind === 'image' ? config.image_types[contentType]! : kind === 'video' ? config.video_types[contentType]! : config.audio_types[contentType]!
  if (!extensions.some((extension) => file.name.toLowerCase().endsWith(extension.toLowerCase()))) {
    throw new Error('文件后缀与文件类型不匹配，请重新选择文件')
  }
  if (!Number.isSafeInteger(file.size) || file.size <= 0) throw new Error('不能上传空文件')
  const maxBytes = kind === 'image' ? config.image_max_bytes : kind === 'video' ? config.video_max_bytes : config.audio_max_bytes
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) throw new Error('上传大小限制无效，请重新加载上传配置')
  if (file.size > maxBytes) throw new Error(`文件过大，${kind === 'image' ? '图片' : kind === 'audio' ? '音频' : '视频'}不能超过 ${(maxBytes / 1024 / 1024).toLocaleString('zh-CN', { maximumFractionDigits: 1 })} MB`)
  return { kind, contentType }
}

function cancelled() {
  return new DOMException('上传已取消', 'AbortError')
}

/** Application credentials go only to requestPolicy; OSS receives a fresh form request. */
export async function uploadMedia(file: File, options: UploadOptions): Promise<UploadedMedia> {
  const { signal, onProgress } = options
  if (signal?.aborted) throw cancelled()
  const { kind, contentType } = validateMediaFile(file, options.config, options.kind)
  onProgress?.(0)
  let policy: UploadPolicy
  try {
    policy = await options.requestPolicy({ filename: file.name, size: file.size, content_type: contentType }, signal)
  } catch (error) {
    if (signal?.aborted) throw cancelled()
    throw error
  }
  if (signal?.aborted) throw cancelled()
  await new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest()
    let settled = false
    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      signal?.removeEventListener('abort', abort)
      request.onload = request.onerror = request.onabort = request.ontimeout = null
      request.upload.onprogress = null
      if (error) reject(error)
      else resolve()
    }
    const abort = () => {
      request.abort()
      finish(cancelled())
    }
    request.open('POST', policy.upload_url)
    request.timeout = 600000
    request.withCredentials = false
    request.upload.onprogress = (event) => {
      if (!settled && event.lengthComputable && event.total > 0) onProgress?.(Math.min(99, Math.round(event.loaded / event.total * 100)))
    }
    request.onload = () => {
      if (signal?.aborted) finish(cancelled())
      else if (request.status === 200 || request.status === 201) finish()
      else finish(new Error(`文件上传失败（HTTP ${request.status}），请重试`))
    }
    request.onerror = () => finish(new Error('文件上传失败，请检查网络和上传服务配置后重试'))
    request.ontimeout = () => finish(new Error('文件上传超时，请重试'))
    request.onabort = () => finish(cancelled())
    signal?.addEventListener('abort', abort, { once: true })
    if (signal?.aborted) { abort(); return }
    const form = new FormData()
    for (const [name, value] of Object.entries(policy.fields)) form.append(name, value)
    form.append('file', file.type === contentType ? file : new File([file], file.name, { type: contentType }))
    try { request.send(form) } catch { finish(new Error('文件上传失败，请检查上传服务地址后重试')) }
  })
  if (signal?.aborted) throw cancelled()
  onProgress?.(100)
  return { url: policy.public_url, key: policy.key, kind }
}
