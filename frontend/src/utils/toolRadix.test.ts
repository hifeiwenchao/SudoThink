import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { convertRadix } from './tools/radix'

describe('integer radix conversion', () => {
  it('accepts 4096 digits plus a sign and matching prefix but bounds larger inputs', () => {
    const result = convertRadix('-0x' + 'F'.repeat(4096), 16)
    assert.equal(result.hexadecimal, '-' + 'F'.repeat(4096))
    assert.equal(result.binary, '-' + '1'.repeat(16384))
    assert.throws(() => convertRadix('F'.repeat(4097), 16), /4096|过长/)
    assert.throws(() => convertRadix('-0x' + 'F'.repeat(4097), 16), /4096|4099|过长/)
    assert.throws(() => convertRadix('1'.padStart(4100, ' '), 10), /4099|过长/)
  })

  it('converts a large integer without losing precision', () => {
    assert.deepEqual(convertRadix('9007199254740993', 10), {
      binary: '100000000000000000000000000000000000000000000000000001',
      octal: '400000000000000001',
      decimal: '9007199254740993',
      hexadecimal: '20000000000001',
    })
  })

  it('converts signed values and matching prefixes in all supported bases', () => {
    for (const [text, base] of [['-0b11111111', 2], ['-0o377', 8], ['-255', 10], ['-0Xff', 16]] as const) {
      assert.deepEqual(convertRadix(text, base), { binary: '-11111111', octal: '-377', decimal: '-255', hexadecimal: '-FF' })
    }
    assert.equal(convertRadix(' +000255 ', 10).hexadecimal, 'FF')
    assert.equal(convertRadix('-0', 2).decimal, '0')
    assert.equal(convertRadix('010', 10).decimal, '10')
  })

  it('rejects digits outside the selected base and conflicting prefixes', () => {
    for (const [text, base] of [['102', 2], ['08', 8], ['fg', 16], ['0x10', 10], ['0b10', 16], ['0o10', 2]] as const) {
      assert.throws(() => convertRadix(text, base), /数位|前缀/)
    }
  })

  it('rejects empty input, decimals, exponents, separators, and unsupported bases', () => {
    for (const text of ['', ' ', '+', '--1', '0x', '1.2', '1e3', '1_000', '1 0']) {
      assert.throws(() => convertRadix(text, 10), /整数|数位|前缀/)
    }
    assert.throws(() => convertRadix('10', 3), /进制/)
  })
})
