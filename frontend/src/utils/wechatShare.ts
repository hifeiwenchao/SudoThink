export interface WechatSharePayload {
  title: string
  desc: string
  link: string
  imgUrl: string
}

export interface WechatSignature {
  app_id: string
  timestamp: number
  nonce_str: string
  signature: string
}

export interface WechatSdk {
  config(options: {
    debug: boolean
    appId: string
    timestamp: number
    nonceStr: string
    signature: string
    jsApiList: string[]
  }): void
  ready(callback: () => void): void
  error(callback: (error: unknown) => void): void
  updateAppMessageShareData(options: WechatSharePayload, callback?: () => void): void
  updateTimelineShareData(options: WechatSharePayload, callback?: () => void): void
}

declare global {
  interface Window {
    wx?: WechatSdk
  }
}

const WECHAT_SDK_URL = 'https://res.wx.qq.com/open/js/jweixin-1.6.0.js'
let sdkPromise: Promise<WechatSdk> | null = null

export function isWeChatBrowser(userAgent = typeof navigator === 'undefined' ? '' : navigator.userAgent): boolean {
  return /MicroMessenger/i.test(userAgent)
}

export function getSharePageUrl(url: string): string {
  return url.split('#', 1)[0] || url
}

function resolveImageUrl(cover: string, link: string): string {
  const source = cover.trim()
  if (!source) return ''
  try {
    return new URL(source, link).href
  } catch {
    return ''
  }
}

export function buildWechatSharePayload(input: {
  title: string
  summary?: string
  url: string
  cover?: string
}): WechatSharePayload {
  const title = input.title.trim()
  return {
    title,
    desc: input.summary?.trim() || title,
    link: getSharePageUrl(input.url),
    imgUrl: resolveImageUrl(input.cover || '', input.url),
  }
}

export function loadWechatSdk(doc: Document = document): Promise<WechatSdk> {
  if (typeof window !== 'undefined' && window.wx) return Promise.resolve(window.wx)
  if (sdkPromise) return sdkPromise

  sdkPromise = new Promise<WechatSdk>((resolve, reject) => {
    const existing = doc.querySelector<HTMLScriptElement>(`script[src="${WECHAT_SDK_URL}"]`)
    const script = existing || doc.createElement('script')
    const finish = () => {
      if (typeof window !== 'undefined' && window.wx) resolve(window.wx)
      else reject(new Error('微信 SDK 加载完成，但未找到 wx 接口'))
    }
    script.addEventListener('load', finish, { once: true })
    script.addEventListener('error', () => reject(new Error('微信 SDK 加载失败')), { once: true })
    if (!existing) {
      script.src = WECHAT_SDK_URL
      script.async = true
      doc.head.appendChild(script)
    }
  }).catch((error) => {
    sdkPromise = null
    throw error
  })
  return sdkPromise
}

export function configureWechatShare(sdk: WechatSdk, signature: WechatSignature, payload: WechatSharePayload): Promise<void> {
  return new Promise((resolve, reject) => {
    let finished = false
    const fail = (error: unknown) => {
      if (finished) return
      finished = true
      reject(error instanceof Error ? error : new Error('微信分享配置失败'))
    }
    sdk.error(fail)
    sdk.ready(() => {
      if (finished) return
      try {
        sdk.updateAppMessageShareData(payload)
        sdk.updateTimelineShareData(payload)
        finished = true
        resolve()
      } catch (error) {
        fail(error)
      }
    })
    try {
      sdk.config({
        debug: false,
        appId: signature.app_id,
        timestamp: signature.timestamp,
        nonceStr: signature.nonce_str,
        signature: signature.signature,
        jsApiList: ['updateAppMessageShareData', 'updateTimelineShareData'],
      })
    } catch (error) {
      fail(error)
    }
  })
}
