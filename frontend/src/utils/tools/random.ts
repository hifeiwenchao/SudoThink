export interface RandomOptions {
  min: string
  max: string
  count: number
  kind: 'integer' | 'decimal'
  precision: number
  allowDuplicates: boolean
  sort: 'none' | 'ascending' | 'descending'
}

const MAX_SCALED_VALUE = BigInt(Number.MAX_SAFE_INTEGER)

function parseEndpoint(input: string, precision: number): bigint {
  const source = input.trim()
  if (source.length > 64) throw new Error('数值范围过大，请缩小数值或小数精度')
  const match = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))$/.exec(source)
  if (!match || !Number.isFinite(Number(source))) throw new Error('请输入有限的十进制数值')
  const fraction = (match[3] ?? match[4] ?? '').replace(/0+$/, '')
  if (fraction.length > precision) {
    throw new Error(precision === 0 ? '整数模式的最小值和最大值必须是整数' : `端点必须符合 ${precision} 位小数精度`)
  }
  const magnitude = BigInt(match[2] ?? '0') * 10n ** BigInt(precision) + BigInt(fraction.padEnd(precision, '0') || '0')
  if (magnitude > MAX_SCALED_VALUE) throw new Error('数值范围过大，请缩小数值或小数精度')
  return match[1] === '-' ? -magnitude : magnitude
}

function fillSecureRandom(array: Uint32Array): void {
  if (!globalThis.crypto?.getRandomValues) throw new Error('当前浏览器不支持安全随机数生成')
  globalThis.crypto.getRandomValues(array)
}

function randomBelow(limit: bigint, fillRandom: (array: Uint32Array) => void): bigint {
  if (limit === 1n) return 0n
  const bits = (limit - 1n).toString(2).length
  const mask = (1n << BigInt(bits)) - 1n
  const words = new Uint32Array(Math.ceil(bits / 32))
  // Mask to the required bit width, then reject out-of-range draws. Using
  // value % limit directly would favor some outcomes when limit is not a power of 2.
  for (let attempt = 0; attempt < 128; attempt++) {
    fillRandom(words)
    let value = 0n
    for (const word of words) value = (value << 32n) | BigInt(word)
    value &= mask
    if (value < limit) return value
  }
  throw new Error('随机数生成失败，请重试')
}

function formatScaled(value: bigint, precision: number): string {
  if (precision === 0) return value.toString()
  const absolute = (value < 0n ? -value : value).toString().padStart(precision + 1, '0')
  return `${value < 0n ? '-' : ''}${absolute.slice(0, -precision)}.${absolute.slice(-precision)}`
}

export function generateRandomNumbers(options: RandomOptions, fillRandom = fillSecureRandom): { values: string[]; rule: string } {
  if (!Number.isInteger(options.count) || options.count < 1 || options.count > 1000) throw new Error('生成数量必须是 1 至 1000 的整数')
  if (options.kind !== 'integer' && options.kind !== 'decimal') throw new Error('请选择整数或小数模式')
  if (!['none', 'ascending', 'descending'].includes(options.sort)) throw new Error('请选择有效的排序方式')
  const precision = options.kind === 'integer' ? 0 : options.precision
  if (!Number.isInteger(precision) || precision < 0 || precision > 8) throw new Error('小数精度必须是 0 至 8 的整数')
  const min = parseEndpoint(options.min, precision)
  const max = parseEndpoint(options.max, precision)
  if (min > max) throw new Error('最小值不能大于最大值')
  const capacity = max - min + 1n
  if (!options.allowDuplicates && BigInt(options.count) > capacity) throw new Error(`可用数值数量不足：当前范围仅有 ${capacity} 个不同数值`)

  const values: bigint[] = []
  // A sparse partial Fisher-Yates shuffle selects unique values in O(count),
  // even if the request consumes the complete range.
  const swaps = new Map<bigint, bigint>()
  let remaining = capacity
  for (let index = 0; index < options.count; index++) {
    if (options.allowDuplicates) {
      values.push(min + randomBelow(capacity, fillRandom))
    } else {
      const selectedIndex = randomBelow(remaining, fillRandom)
      const selectedValue = swaps.get(selectedIndex) ?? selectedIndex
      const lastIndex = remaining - 1n
      swaps.set(selectedIndex, swaps.get(lastIndex) ?? lastIndex)
      swaps.delete(lastIndex)
      values.push(min + selectedValue)
      remaining--
    }
  }
  if (options.sort !== 'none') {
    const direction = options.sort === 'ascending' ? 1 : -1
    values.sort((left, right) => left < right ? -direction : left > right ? direction : 0)
  }
  const kind = options.kind === 'integer' ? '整数' : `${precision} 位小数`
  const sorting = { none: '保留生成顺序', ascending: '升序', descending: '降序' }[options.sort]
  return {
    values: values.map(value => formatScaled(value, precision)),
    rule: `${formatScaled(min, precision)} 至 ${formatScaled(max, precision)}（含端点）· ${kind} · ${options.count} 个 · ${options.allowDuplicates ? '允许重复' : '不重复'} · ${sorting}`,
  }
}
