export interface RandomStringOptions {
  length: number
  count: number
  lowercase: boolean
  uppercase: boolean
  digits: boolean
  symbols: boolean
  customCharacters: string
  excludedCharacters: string
  excludeSimilar: boolean
  allowRepeatedCharacters: boolean
  prefix: string
  suffix: string
}

const LOWERCASE = 'abcdefghijklmnopqrstuvwxyz'
const UPPERCASE = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
const DIGITS = '0123456789'
const SYMBOLS = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
const SIMILAR_CHARACTERS = '0Oo1Il'
const INVALID_CHARACTER = /[\p{White_Space}\p{Cc}\p{Cf}\p{Cs}\p{Default_Ignorable_Code_Point}]/u
const INVALID_AFFIX = /[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}\p{Default_Ignorable_Code_Point}]/u

function validateCharacterInput(value: string, label: string): void {
  if (value.length > 1024) throw new Error(`${label}最多为 1024 个 UTF-16 单位`)
  if (INVALID_CHARACTER.test(value)) throw new Error(`${label}不能包含空白、控制、不可见格式字符或无效字符`)
}

export function resolveRandomCharacters(options: RandomStringOptions): string[] {
  validateCharacterInput(options.customCharacters, '自定义字符')
  validateCharacterInput(options.excludedCharacters, '排除字符')
  const sources = [
    options.lowercase ? LOWERCASE : '',
    options.uppercase ? UPPERCASE : '',
    options.digits ? DIGITS : '',
    options.symbols ? SYMBOLS : '',
    options.customCharacters,
  ].join('')
  const excluded = new Set(Array.from(options.excludedCharacters + (options.excludeSimilar ? SIMILAR_CHARACTERS : '')))
  const characters = Array.from(new Set(Array.from(sources))).filter(character => !excluded.has(character))
  if (!characters.length) throw new Error('没有可用字符，请选择字符类型或添加自定义字符，并检查排除规则')
  return characters
}

function validateAffix(value: string, label: string): void {
  if (value.length > 64) throw new Error(`${label}最多为 64 个 UTF-16 单位`)
  if (INVALID_AFFIX.test(value)) throw new Error(`${label}不能包含换行、控制、不可见格式字符或无效字符`)
}

function fillSecureRandom(array: Uint32Array): void {
  if (!globalThis.crypto?.getRandomValues) throw new Error('当前浏览器不支持安全随机字符串生成')
  globalThis.crypto.getRandomValues(array)
}

function createRandomIndex(fillRandom: (array: Uint32Array) => void): (limit: number) => number {
  const words = new Uint32Array(64)
  let cursor = words.length
  return (limit: number): number => {
    if (limit === 1) return 0
    const mask = 2 ** Math.ceil(Math.log2(limit)) - 1
    // Keep uniform low bits and reject excess indices instead of using biased
    // modulo reduction. Buffering keeps large requests from calling crypto per character.
    for (let attempt = 0; attempt < 128; attempt++) {
      if (cursor === words.length) {
        fillRandom(words)
        cursor = 0
      }
      const value = words[cursor++]! & mask
      if (value < limit) return value
    }
    throw new Error('随机字符串生成失败，请重试')
  }
}

export function generateRandomStrings(
  options: RandomStringOptions,
  fillRandom = fillSecureRandom,
): { values: string[]; rule: string; alphabet: string } {
  if (!Number.isInteger(options.length) || options.length < 1 || options.length > 256) {
    throw new Error('随机部分长度必须是 1 至 256 的整数')
  }
  if (!Number.isInteger(options.count) || options.count < 1 || options.count > 100) {
    throw new Error('生成数量必须是 1 至 100 的整数')
  }
  const characters = resolveRandomCharacters(options)
  validateAffix(options.prefix, '前缀')
  validateAffix(options.suffix, '后缀')
  if (!options.allowRepeatedCharacters && options.length > characters.length) {
    throw new Error(`不重复时随机长度不能超过 ${characters.length} 个可用字符`)
  }
  const randomIndex = createRandomIndex(fillRandom)
  const values: string[] = []
  for (let row = 0; row < options.count; row++) {
    const pool = options.allowRepeatedCharacters ? characters : characters.slice()
    const parts: string[] = []
    for (let index = 0; index < options.length; index++) {
      const selectedIndex = randomIndex(pool.length)
      parts.push(pool[selectedIndex]!)
      if (!options.allowRepeatedCharacters) {
        // Partial Fisher-Yates: remove a sampled character in constant time.
        // Filling the whole pool never requires waiting for a fresh collision-free draw.
        pool[selectedIndex] = pool[pool.length - 1]!
        pool.pop()
      }
    }
    values.push(options.prefix + parts.join('') + options.suffix)
  }
  return {
    values,
    alphabet: characters.join(''),
    rule: `每条随机部分 ${options.length} 个字符 · ${options.count} 条 · ${characters.length} 个可用字符 · 随机部分${options.allowRepeatedCharacters ? '允许字符重复' : '字符不重复'} · 多条结果可相同${options.prefix || options.suffix ? ' · 固定前后缀不计随机长度及重复规则' : ''}`,
  }
}
