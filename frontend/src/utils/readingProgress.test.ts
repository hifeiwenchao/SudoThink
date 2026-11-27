import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readingProgress } from './readingProgress'

test('body progress clamps before and after long content and measures the reading viewport', () => {
  assert.equal(readingProgress(900, 2000, 800), 0)
  assert.equal(readingProgress(120, 2000, 800), 0)
  assert.equal(readingProgress(-540, 2000, 800), 50)
  assert.equal(readingProgress(-1200, 2000, 800), 100)
  assert.equal(readingProgress(-3000, 2000, 800), 100)
})

test('short content has useful finite progress without headings or division by zero', () => {
  assert.equal(readingProgress(900, 200, 800), 0)
  assert.equal(readingProgress(500, 200, 800), 50)
  assert.equal(readingProgress(120, 200, 800), 100)
  assert.equal(readingProgress(120, 0, 800), 100)
  assert.equal(readingProgress(Number.NaN, 200, 800), 0)
})
