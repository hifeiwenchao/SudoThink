import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { transformJson } from './tools/json'

describe('JSON tool', () => {
  it('formats nested JSON with the requested indentation and Unicode intact', () => {
    assert.equal(transformJson('{"名字":"你好","列表":[1,null]}', 'format', 2), '{\n  "名字": "你好",\n  "列表": [\n    1,\n    null\n  ]\n}')
    assert.equal(transformJson('{"a":1}', 'format', 4), '{\n    "a": 1\n}')
  })

  it('compresses arrays and null without changing their JSON value', () => {
    assert.equal(transformJson('[ 1, "中 文", null ]', 'compact'), '[1,"中 文",null]')
    assert.equal(transformJson(' null ', 'compact'), 'null')
  })

  it('serializes raw text to a JSON string and restores the exact original text', () => {
    const original = '第一行\n"你好"\\路径 😀'
    const serialized = transformJson(original, 'serialize')
    assert.equal(serialized, '"第一行\\n\\"你好\\"\\\\路径 😀"')
    assert.equal(transformJson(serialized, 'deserialize'), original)
  })

  it('requires a JSON string when restoring text', () => {
    for (const input of ['{}', '[1]', 'null', '2', 'true']) {
      assert.throws(() => transformJson(input, 'deserialize'), /JSON 字符串/)
    }
  })

  it('validates all JSON values and reports syntax errors without executing JavaScript', () => {
    assert.match(transformJson('false', 'validate'), /有效/)
    assert.match(transformJson('null', 'validate'), /有效/)
    for (const input of ['{bad:true}', '{"a":1,}', 'undefined', '(()=>1)()', '']) {
      assert.throws(() => transformJson(input, 'format'), /JSON|输入/)
    }
  })

  it('bounds input size for every operation', () => {
    assert.throws(() => transformJson('a'.repeat(1_000_001), 'serialize'), /过大/)
  })

  it('preserves large integers, high precision decimals, and exponent notation', () => {
    assert.equal(transformJson('{"id":9007199254740993,"value":0.123456789012345678901,"large":1e400}', 'format'), '{\n  "id": 9007199254740993,\n  "value": 0.123456789012345678901,\n  "large": 1e400\n}')
    assert.equal(transformJson('[ 9007199254740993, 0.123456789012345678901, 1e400 ]', 'compact'), '[9007199254740993,0.123456789012345678901,1e400]')
  })

  it('rejects nesting beyond 128 containers before invoking recursive parsing', () => {
    const source = '['.repeat(129) + '0' + ']'.repeat(129)
    for (const operation of ['validate', 'format', 'compact', 'deserialize'] as const) {
      assert.throws(() => transformJson(source, operation), /嵌套.*128/)
    }
  })

  it('accepts 128 nested containers and ignores brackets and escaped quotes inside strings', () => {
    const text = '括号' + '[{'.repeat(200) + '"引号"\\尾巴' + '}]'.repeat(200)
    const inner = JSON.stringify({ text, trailingSlash: '\\', values: [] })
    const source = '['.repeat(126) + inner + ']'.repeat(126)
    assert.equal(transformJson(source, 'compact'), source)
    assert.match(transformJson(source, 'format', 4), /尾巴/)
    assert.equal(transformJson('['.repeat(129), 'serialize'), '"' + '['.repeat(129) + '"')
  })

  it('rejects indentation expansion past 2 million output characters', () => {
    const source = '['.repeat(80) + '0,'.repeat(10_000) + '0' + ']'.repeat(80)
    assert.throws(() => transformJson(source, 'format', 4), /输出.*2,000,000/)
    assert.equal(transformJson(source, 'compact'), source)
  })

  it('accounts for string escaping and accepts the exact output budget boundary', () => {
    assert.equal(transformJson('\u0000'.repeat(333_333), 'serialize').length, 2_000_000)
    assert.throws(() => transformJson('\u0000'.repeat(333_334), 'serialize'), /输出.*2,000,000/)
    const loneSurrogates = '"' + '\ud800'.repeat(333_333) + '"'
    assert.equal(transformJson(loneSurrogates, 'compact').length, 2_000_000)
    assert.throws(() => transformJson('"' + '\ud800'.repeat(333_334) + '"', 'compact'), /输出.*2,000,000/)
  })
})
