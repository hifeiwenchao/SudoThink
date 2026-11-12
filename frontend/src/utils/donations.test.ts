import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getDonationChannels, isDonationQrUrl } from './donations'

test('URL validation rejects Unicode control and invisible format characters before saving', () => {
  for (const character of ['\u0085', '\u009f', '\u200b', '\u2060']) {
    assert.equal(isDonationQrUrl(`https://cdn.example.com/${character}code.png`), false)
  }
})

test('disabled donations do not expose saved collection codes', () => {
  assert.deepEqual(getDonationChannels({ enabled: false, wechat_qr_url: 'https://cdn.example.com/wechat.png', alipay_qr_url: 'https://cdn.example.com/alipay.png' }), [])
})

test('collection codes keep their payment method and trim surrounding whitespace', () => {
  assert.deepEqual(getDonationChannels({ enabled: true, wechat_qr_url: ' https://cdn.example.com/wechat.png ', alipay_qr_url: 'https://cdn.example.com/alipay.png?size=800' }), [
    { key: 'wechat', label: '微信', url: 'https://cdn.example.com/wechat.png' },
    { key: 'alipay', label: '支付宝', url: 'https://cdn.example.com/alipay.png?size=800' },
  ])
})

test('either payment method can be configured on its own', () => {
  assert.deepEqual(getDonationChannels({ enabled: true, wechat_qr_url: '', alipay_qr_url: 'http://localhost:8100/alipay.png' }), [
    { key: 'alipay', label: '支付宝', url: 'http://localhost:8100/alipay.png' },
  ])
})

test('no settings or empty collection codes leave the support entry hidden', () => {
  assert.deepEqual(getDonationChannels(null), [])
  assert.deepEqual(getDonationChannels({ enabled: true, wechat_qr_url: '', alipay_qr_url: '  ' }), [])
})

test('unsafe collection URLs are omitted while a valid alternative remains available', () => {
  for (const url of ['javascript:alert(1)', 'data:image/png;base64,AAAA', 'file:///tmp/code.png', '//cdn.example.com/code.png', 'https://user:secret@cdn.example.com/code.png', 'https://cdn.example.com/a b.png', 'https://cdn.example.com/\\code.png', 'https://cdn.example.com/code.png#fragment', 'https://cdn.example.com/\u0000.png']) {
    assert.deepEqual(getDonationChannels({ enabled: true, wechat_qr_url: url, alipay_qr_url: 'https://cdn.example.com/alipay.png' }), [
      { key: 'alipay', label: '支付宝', url: 'https://cdn.example.com/alipay.png' },
    ])
  }
})
