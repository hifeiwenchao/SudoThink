export const MAX_RADIX_DIGITS = 4096
export const MAX_RADIX_INPUT_LENGTH = MAX_RADIX_DIGITS + 3

export function convertRadix(input: string, base: number) {
  if (![2, 8, 10, 16].includes(base)) throw new Error('仅支持二、八、十、十六进制')
  if (input.length > MAX_RADIX_INPUT_LENGTH) throw new Error('整数输入过长，最多 4099 个字符（含符号、前缀及空白）')
  const match = /^([+-]?)(.+)$/.exec(input.trim())
  if (!match) throw new Error('请输入一个整数')
  let digits = match[2]
  const prefix = /^0([box])/i.exec(digits)
  const prefixes: Record<string, number> = { b: 2, o: 8, x: 16 }
  if (prefix) {
    if (prefixes[prefix[1].toLowerCase()] !== base) throw new Error('数字前缀与所选进制冲突')
    digits = digits.slice(2)
  }
  if (digits.length > MAX_RADIX_DIGITS) throw new Error('整数输入过长，最多 4096 个数位（不含符号和前缀）')
  if (!digits || !/^[0-9a-f]+$/i.test(digits) || [...digits].some(char => Number.parseInt(char, 16) >= base)) {
    throw new Error(`包含无效数位，请输入合法的${base}进制整数（不支持小数、指数或分隔符）`)
  }
  const bigintPrefix = base === 2 ? '0b' : base === 8 ? '0o' : base === 16 ? '0x' : ''
  const magnitude = BigInt(bigintPrefix + digits)
  const value = match[1] === '-' ? -magnitude : magnitude
  return {
    binary: value.toString(2),
    octal: value.toString(8),
    decimal: value.toString(10),
    hexadecimal: value.toString(16).toUpperCase(),
  }
}
