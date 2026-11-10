import { isLosslessNumber, parse, stringify } from 'lossless-json'

export type JsonOperation = 'validate' | 'format' | 'compact' | 'serialize' | 'deserialize'

const MAX_INPUT_LENGTH = 1_000_000
const MAX_OUTPUT_LENGTH = 2_000_000
const MAX_NESTING_DEPTH = 128

function assertNestingDepth(input: string): void {
  let depth = 0
  let inString = false
  let escaped = false
  for (const character of input) {
    if (inString) {
      if (escaped) escaped = false
      else if (character === '\\') escaped = true
      else if (character === '"') inString = false
    } else if (character === '"') {
      inString = true
    } else if (character === '[' || character === '{') {
      if (++depth > MAX_NESTING_DEPTH) throw new Error('JSON 嵌套过深，最多支持 128 层数组或对象')
    } else if (character === ']' || character === '}') {
      depth--
    }
  }
}

// Count JSON.stringify's string escaping without allocating the escaped string.
function serializedStringLength(value: string): number {
  let length = 2
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index)
    if (code === 34 || code === 92 || code === 8 || code === 9 || code === 10 || code === 12 || code === 13) {
      length += 2
    } else if (code < 32) {
      length += 6
    } else if (code >= 0xd800 && code <= 0xdbff) {
      const nextCode = value.charCodeAt(index + 1)
      if (nextCode >= 0xdc00 && nextCode <= 0xdfff) { length += 2; index++ }
      else length += 6
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      length += 6
    } else {
      length++
    }
  }
  return length
}

function assertOutputBudget(value: unknown, indent: number): void {
  let length = 0
  function add(amount: number) {
    length += amount
    if (length > MAX_OUTPUT_LENGTH) throw new Error('处理后的输出超过 2,000,000 个字符，请减少内容或改用压缩')
  }
  function visit(candidate: unknown, depth: number): void {
    if (typeof candidate === 'string') {
      add(serializedStringLength(candidate))
    } else if (isLosslessNumber(candidate)) {
      add(candidate.toString().length)
    } else if (candidate === null) {
      add(4)
    } else if (typeof candidate === 'boolean') {
      add(candidate ? 4 : 5)
    } else if (Array.isArray(candidate)) {
      add(2 + Math.max(0, candidate.length - 1))
      if (indent && candidate.length) add(candidate.length + 1 + indent * ((depth + 1) * candidate.length + depth))
      for (const child of candidate) visit(child, depth + 1)
    } else if (candidate && typeof candidate === 'object') {
      const keys = Object.keys(candidate)
      add(2 + Math.max(0, keys.length - 1) + keys.length)
      if (indent && keys.length) add(keys.length * 2 + 1 + indent * ((depth + 1) * keys.length + depth))
      for (const key of keys) {
        add(serializedStringLength(key))
        visit((candidate as Record<string, unknown>)[key], depth + 1)
      }
    }
  }
  visit(value, 0)
}

export function transformJson(input: string, operation: JsonOperation, indent: 2 | 4 = 2): string {
  if (input.length > MAX_INPUT_LENGTH) throw new Error('输入过大，最多处理 1,000,000 个字符')
  if (operation === 'serialize') {
    assertOutputBudget(input, 0)
    return JSON.stringify(input)
  }
  if (!input.trim()) throw new Error('请输入 JSON 内容')
  assertNestingDepth(input)
  try {
    const value = parse(input)
    switch (operation) {
      case 'validate': return 'JSON 有效，语法检查通过。'
      case 'format':
        assertOutputBudget(value, indent)
        return stringify(value, null, indent) ?? ''
      case 'compact':
        assertOutputBudget(value, 0)
        return stringify(value) ?? ''
      case 'deserialize':
        if (typeof value !== 'string') throw new Error('还原文本需要输入一个 JSON 字符串，例如 "你好\\n世界"')
        return value
      default: throw new Error('不支持的 JSON 操作')
    }
  } catch (error) {
    if (error instanceof SyntaxError) throw new Error(`JSON 语法错误：${error.message}`)
    if (error instanceof RangeError) throw new Error('JSON 层级过深，请减少嵌套后重试')
    throw error
  }
}
