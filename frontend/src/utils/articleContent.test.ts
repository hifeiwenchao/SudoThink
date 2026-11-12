import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { JSDOM } from 'jsdom'

const { window } = new JSDOM('')
Object.assign(globalThis, { window, document: window.document, DOMParser: window.DOMParser })
const { getArticleText, hasArticleContent, toArticleHtml, sanitizeArticleHtml } = await import('./articleContent')

describe('article content', () => {
  it('pastes clipboard HTML as readable content instead of escaped markup', () => {
    const html = sanitizeArticleHtml('<span style="color:red">从浏览器复制</span><custom>文本</custom>')
    const body = new DOMParser().parseFromString(html, 'text/html').body
    assert.equal(body.textContent, '从浏览器复制文本')
    assert.equal(body.querySelector('custom'), null)
    assert.equal(body.querySelector('[style]'), null)
  })
  it('preserves formatting while removing executable HTML and unsafe links', () => {
    const html = toArticleHtml('<h2>标题</h2><p><strong>正文</strong><script>alert(1)</script><a href="javascript:alert(1)">链接</a><img src="https://example.com/a.png" onerror="alert(1)"></p>')
    const document = new DOMParser().parseFromString(html, 'text/html')
    assert.equal(document.querySelector('h2')?.textContent, '标题')
    assert.equal(document.querySelector('strong')?.textContent, '正文')
    assert.equal(document.querySelector('script'), null)
    assert.equal(document.querySelector('a')?.hasAttribute('href'), false)
    assert.equal(document.querySelector('img')?.hasAttribute('onerror'), false)
  })

  it('retains text alignment without retaining arbitrary CSS', () => {
    const html = toArticleHtml('<p style="text-align: center; background-image: url(https://example.com/track)">居中</p>')
    const paragraph = new DOMParser().parseFromString(html, 'text/html').querySelector('p')!
    assert.equal(paragraph.style.textAlign, 'center')
    assert.equal(paragraph.style.backgroundImage, '')
  })

  it('keeps legacy plain text and line breaks without interpreting angle brackets', () => {
    const html = toArticleHtml('条件：a < b && b > c\n第二行\n\n新的段落 <example>')
    const body = new DOMParser().parseFromString(html, 'text/html').body
    assert.equal(body.querySelectorAll('p').length, 2)
    assert.equal(body.querySelectorAll('br').length, 1)
    assert.equal(body.textContent, '条件：a < b && b > c第二行新的段落 <example>')
  })

  for (const content of ['', '<p></p>', '<p><br></p>', '<p> &nbsp; \u200b</p>', '<p><img src="javascript:alert(1)"></p>']) {
    it(`rejects visually empty content: ${content}`, () => {
      assert.equal(hasArticleContent(content), false)
    })
  }

  it('accepts a safe image-only article', () => {
    assert.equal(hasArticleContent('<p><img src="https://example.com/a.png" alt="插图"></p>'), true)
  })

  it('preserves a video-only article with safe playback defaults and no word count', () => {
    const source = '<video src="https://cdn.example.com/clip.mp4" autoplay loop onerror="alert(1)">浏览器不支持视频</video>'
    const html = toArticleHtml(source)
    const video = new DOMParser().parseFromString(html, 'text/html').querySelector('video')!
    assert.ok(video)
    assert.equal(video.getAttribute('src'), 'https://cdn.example.com/clip.mp4')
    assert.equal(video.hasAttribute('controls'), true)
    assert.equal(video.getAttribute('preload'), 'metadata')
    assert.equal(video.hasAttribute('playsinline'), true)
    assert.equal(video.hasAttribute('autoplay'), false)
    assert.equal(video.hasAttribute('loop'), false)
    assert.equal(video.hasAttribute('onerror'), false)
    assert.equal(hasArticleContent(source), true)
    assert.equal(getArticleText(source), '')
  })

  for (const src of ['javascript:alert(1)', 'data:video/mp4;base64,YQ==', 'blob:https://example.com/id', '//example.com/video.mp4', '']) {
    it(`removes a video with unsafe or missing source: ${src}`, () => {
      const html = sanitizeArticleHtml(`<video src="${src}" controls></video>`)
      assert.equal(new DOMParser().parseFromString(html, 'text/html').querySelector('video'), null)
      assert.equal(hasArticleContent(`<video src="${src}"></video>`), false)
    })
  }

  it('retains safe site-relative video sources without enabling embeds', () => {
    const html = sanitizeArticleHtml('<video src="/media/clip.webm"></video><iframe src="https://example.com"></iframe><object data="https://example.com"></object>')
    const body = new DOMParser().parseFromString(html, 'text/html').body
    assert.equal(body.querySelector('video')?.getAttribute('src'), '/media/clip.webm')
    assert.equal(body.querySelector('iframe, object'), null)
  })

  it('extracts readable text with boundaries between paragraphs', () => {
    assert.equal(getArticleText('<h2>你好</h2><p>世界 <strong>Vue</strong></p>'), '你好\n世界 Vue')
  })

  it('opens external links without giving them access to the opener', () => {
    const html = toArticleHtml('<p><a href="https://example.com">参考</a></p>')
    const link = new DOMParser().parseFromString(html, 'text/html').querySelector('a')!
    assert.equal(link.target, '_blank')
    assert.ok(link.rel.includes('noopener'))
    assert.ok(link.rel.includes('noreferrer'))
  })
})
