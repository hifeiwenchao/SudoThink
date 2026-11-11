import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import * as random from './tools/random'
import type { RandomStringOptions } from './tools/random'

const defaults: RandomStringOptions = {
  length: 12,
  count: 5,
  lowercase: true,
  uppercase: true,
  digits: true,
  symbols: false,
  customCharacters: '',
  excludedCharacters: '',
  excludeSimilar: false,
  allowRepeatedCharacters: true,
  prefix: '',
  suffix: '',
}

const customOnly = (customCharacters: string, options: Partial<RandomStringOptions> = {}): RandomStringOptions => ({
  ...defaults, lowercase: false, uppercase: false, digits: false, customCharacters, ...options,
})

const unexpectedEntropy = () => { throw new Error('不应读取随机源') }

describe('random string tool', () => {
  it('combines only selected built-in sets including all printable ASCII punctuation', () => {
    assert.equal(random.resolveRandomCharacters({ ...defaults, uppercase: false, digits: false }).join(''), 'abcdefghijklmnopqrstuvwxyz')
    assert.equal(random.resolveRandomCharacters({ ...defaults, lowercase: false, digits: false }).join(''), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    assert.equal(random.resolveRandomCharacters({ ...defaults, lowercase: false, uppercase: false }).join(''), '0123456789')
    const punctuation = random.resolveRandomCharacters(customOnly('', { symbols: true }))
    assert.equal(punctuation.length, 32)
    assert.match(punctuation.join(''), /^[!-~]+$/)
    assert.doesNotMatch(punctuation.join(''), /[a-zA-Z0-9]/)
    assert.equal(random.resolveRandomCharacters({ ...defaults, symbols: true }).length, 94)
  })

  it('uses secure browser randomness to generate the requested number and length', () => {
    const result = random.generateRandomStrings(defaults)
    assert.equal(result.values.length, 5)
    for (const value of result.values) assert.match(value, /^[a-zA-Z0-9]{12}$/)
    assert.match(result.rule, /12/)
    assert.match(result.rule, /5/)
  })

  it('deduplicates Unicode code points across custom and built-in characters before excluding them', () => {
    const options = customOnly('a甲😀乙a甲😀', { lowercase: true, excludedCharacters: '乙a乙' })
    const result = random.generateRandomStrings({ ...options, length: 1, count: 1 }, array => { array.fill(0) })
    assert.equal(result.alphabet, 'bcdefghijklmnopqrstuvwxyz甲😀')
    assert.deepEqual(random.resolveRandomCharacters(customOnly('甲😀甲😀乙', { excludedCharacters: '乙' })), ['甲', '😀'])
  })

  it('removes the documented similar characters after combining every source', () => {
    assert.deepEqual(random.resolveRandomCharacters(customOnly('0Oo1Il23iL', { excludeSimilar: true })), ['2', '3', 'i', 'L'])
    assert.doesNotMatch(random.resolveRandomCharacters({ ...defaults, excludeSimilar: true }).join(''), /[0Oo1Il]/)
  })

  it('rejects an empty effective alphabet with a useful error', () => {
    assert.throws(() => random.generateRandomStrings(customOnly('')), /可用字符/)
    assert.throws(() => random.generateRandomStrings(customOnly('甲😀', { excludedCharacters: '甲😀' })), /可用字符/)
    assert.throws(() => random.generateRandomStrings(customOnly('0Oo1Il', { excludeSimilar: true })), /可用字符/)
  })

  it('previews the effective characters independently of unfinished numeric inputs', () => {
    assert.deepEqual(random.resolveRandomCharacters(customOnly('甲😀', { length: Number.NaN, count: 0 })), ['甲', '😀'])
  })

  it('supports single-character alphabets and counts astral characters as one random character', () => {
    const result = random.generateRandomStrings(customOnly('😀', { length: 3, count: 2, prefix: '编号 ', suffix: ' end' }), unexpectedEntropy)
    assert.deepEqual(result.values, ['编号 😀😀😀 end', '编号 😀😀😀 end'])
    assert.equal(result.alphabet, '😀')
  })

  it('keeps prefixes and suffixes outside the length and uniqueness rules, while allowing equal rows', () => {
    const result = random.generateRandomStrings(customOnly('a', {
      length: 1, count: 3, prefix: 'a ', suffix: ' a', allowRepeatedCharacters: false,
    }), unexpectedEntropy)
    assert.deepEqual(result.values, ['a a a', 'a a a', 'a a a'])
    assert.match(result.rule, /随机部分.*不重复/)
    assert.match(result.rule, /多条.*相同/)
    assert.match(result.rule, /前后缀/)
  })

  it('samples the complete Unicode alphabet without collision retries when characters cannot repeat', () => {
    const result = random.generateRandomStrings(customOnly('甲😀乙', { length: 3, count: 4, allowRepeatedCharacters: false }), array => { array.fill(0) })
    for (const value of result.values) {
      assert.equal(Array.from(value).length, 3)
      assert.deepEqual(new Set(Array.from(value)), new Set(['甲', '😀', '乙']))
    }
    assert.throws(() => random.generateRandomStrings(customOnly('甲😀乙', { length: 4, allowRepeatedCharacters: false }), unexpectedEntropy), /不重复.*3|3.*不重复|字符.*不足/)
  })

  it('can consume a 1024-character pool in a single row without requiring lucky random draws', () => {
    const characters = Array.from({ length: 1024 }, (_, index) => String.fromCodePoint(0x4e00 + index)).join('')
    const result = random.generateRandomStrings(customOnly(characters, { length: 1024, count: 1, allowRepeatedCharacters: false }), array => { array.fill(0) })
    assert.equal(Array.from(result.values[0]!).length, 1024)
    assert.equal(new Set(Array.from(result.values[0]!)).size, 1024)
  })

  it('rejects whitespace, control characters, invisible formatting and lone surrogates in character rules', () => {
    for (const unsafe of [' ', '\t', '\n', '\r', '\u00a0', '\u0085', '\u200b', '\u202e', '\ufe0f', '\ud800']) {
      assert.throws(() => random.resolveRandomCharacters(customOnly(`a${unsafe}`)), /空白|不可见|控制|无效/)
      assert.throws(() => random.resolveRandomCharacters(customOnly('a', { excludedCharacters: unsafe })), /空白|不可见|控制|无效/)
    }
  })

  it('bounds each custom or excluded input by UTF-16 length', () => {
    assert.deepEqual(random.resolveRandomCharacters(customOnly('😀'.repeat(512))), ['😀'])
    assert.throws(() => random.resolveRandomCharacters(customOnly('a'.repeat(1025))), /1024/)
    assert.throws(() => random.resolveRandomCharacters(customOnly('a', { excludedCharacters: 'b'.repeat(1025) })), /1024/)
  })

  it('allows spaces in fixed text but rejects line breaks, controls and oversized affixes', () => {
    const result = random.generateRandomStrings(customOnly('a', { length: 1, count: 1, prefix: '😀'.repeat(32), suffix: ' '.repeat(64) }), unexpectedEntropy)
    assert.equal(result.values[0]!.length, 129)
    for (const affix of ['\n', '\r', '\t', '\0', '\u0085', '\u2028', '\u2029', '\u202e', '\ud800']) {
      assert.throws(() => random.generateRandomStrings(customOnly('a', { prefix: affix })), /前缀.*换行|前缀.*控制|前缀.*无效|前缀.*不可见/)
      assert.throws(() => random.generateRandomStrings(customOnly('a', { suffix: affix })), /后缀.*换行|后缀.*控制|后缀.*无效|后缀.*不可见/)
    }
    assert.throws(() => random.generateRandomStrings(customOnly('a', { prefix: 'a'.repeat(65) })), /前缀.*64/)
    assert.throws(() => random.generateRandomStrings(customOnly('a', { suffix: '😀'.repeat(33) })), /后缀.*64/)
  })

  it('rejects invalid length and count before drawing entropy', () => {
    for (const length of [0, -1, 1025, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      assert.throws(() => random.generateRandomStrings({ ...defaults, length }, unexpectedEntropy), /长度.*1.*1024/)
    }
    for (const count of [0, -1, 1001, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      assert.throws(() => random.generateRandomStrings({ ...defaults, count }, unexpectedEntropy), /数量.*1.*1000/)
    }
  })

  it('includes separators and affixes in the total output limit before drawing entropy', () => {
    const accepted = random.generateRandomStrings(customOnly('a', { length: 199, count: 1000 }), unexpectedEntropy)
    assert.equal(accepted.values.join('\n').length, 199999)
    assert.throws(() => random.generateRandomStrings(customOnly('a', { length: 200, count: 1000 }), unexpectedEntropy), /总.*200000|输出.*过大/)
    assert.throws(() => random.generateRandomStrings(customOnly('a', { length: 72, count: 1000, prefix: 'p'.repeat(64), suffix: 's'.repeat(64) }), unexpectedEntropy), /总.*200000|输出.*过大/)
  })

  it('budgets astral characters conservatively as two UTF-16 units', () => {
    assert.equal(random.generateRandomStrings(customOnly('😀', { length: 99, count: 1000 }), unexpectedEntropy).values.join('\n').length, 198999)
    assert.throws(() => random.generateRandomStrings(customOnly('a😀', { length: 100, count: 1000 }), unexpectedEntropy), /总.*200000|输出.*过大/)
  })

  it('rejects out-of-range entropy instead of introducing modulo bias', () => {
    let fills = 0
    const result = random.generateRandomStrings(customOnly('abc', { length: 1, count: 1 }), array => {
      array.fill(fills++ === 0 ? 0xffffffff : 1)
    })
    assert.deepEqual(result.values, ['b'])
  })

  it('stops a consistently rejected random source within a bounded number of attempts', () => {
    let fills = 0
    assert.throws(() => random.generateRandomStrings(customOnly('abc', { length: 1, count: 1 }), array => {
      if (++fills > 128) throw new Error('重试未按上限停止')
      array.fill(0xffffffff)
    }), /随机.*失败/)
    assert.ok(fills > 0 && fills <= 128)
  })
})
