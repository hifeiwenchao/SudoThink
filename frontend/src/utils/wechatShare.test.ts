import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { buildWechatSharePayload, configureWechatShare, getSharePageUrl, isWeChatBrowser, type WechatSdk } from './wechatShare'

describe('wechat share helpers', () => {
  it('detects the WeChat in-app browser without matching ordinary browsers', () => {
    assert.equal(isWeChatBrowser('Mozilla/5.0 MicroMessenger/8.0.50'), true)
    assert.equal(isWeChatBrowser('Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/605.1.15 Safari/605.1.15'), false)
  })

  it('removes the hash before signing the current article URL', () => {
    assert.equal(getSharePageUrl('https://www.example.com/articles/42?from=home#comments'), 'https://www.example.com/articles/42?from=home')
  })

  it('builds share metadata and resolves a relative cover image', () => {
    assert.deepEqual(buildWechatSharePayload({
      title: '一篇文章',
      summary: '文章摘要',
      url: 'https://www.example.com/articles/42',
      cover: '/media/cover.png',
    }), {
      title: '一篇文章',
      desc: '文章摘要',
      link: 'https://www.example.com/articles/42',
      imgUrl: 'https://www.example.com/media/cover.png',
    })
  })

  it('uses the title as a fallback description and leaves an empty cover optional', () => {
    assert.deepEqual(buildWechatSharePayload({
      title: '标题',
      summary: '   ',
      url: 'https://www.example.com/articles/42',
      cover: '',
    }), {
      title: '标题',
      desc: '标题',
      link: 'https://www.example.com/articles/42',
      imgUrl: '',
    })
  })

  it('configures both friend and moments sharing with the backend signature', async () => {
    let ready: (() => void) | undefined
    let config: Record<string, unknown> | undefined
    const calls: string[] = []
    const sdk: WechatSdk = {
      config(options) {
        config = options
        ready?.()
      },
      ready(callback) { ready = callback },
      error() {},
      updateAppMessageShareData() { calls.push('friend') },
      updateTimelineShareData() { calls.push('moments') },
    }

    await configureWechatShare(sdk, {
      app_id: 'wx-test',
      timestamp: 1700000000,
      nonce_str: 'nonce',
      signature: 'signature',
    }, {
      title: '标题',
      desc: '摘要',
      link: 'https://www.example.com/articles/1',
      imgUrl: 'https://cdn.example.com/cover.png',
    })

    assert.deepEqual(config, {
      debug: false,
      appId: 'wx-test',
      timestamp: 1700000000,
      nonceStr: 'nonce',
      signature: 'signature',
      jsApiList: ['updateAppMessageShareData', 'updateTimelineShareData'],
    })
    assert.deepEqual(calls, ['friend', 'moments'])
  })
})
