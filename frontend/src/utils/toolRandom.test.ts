import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { generateRandomNumbers, type RandomOptions } from './tools/random'

const defaults: RandomOptions = {
  min: '1', max: '10', count: 5, kind: 'integer', precision: 2,
  allowDuplicates: true, sort: 'none',
}

describe('random number tool', () => {
  it('includes both decimal endpoints and samples a whole narrow range without retries', () => {
    const result = generateRandomNumbers({ ...defaults, min: '-0.02', max: '0.02', count: 5, kind: 'decimal', precision: 2, allowDuplicates: false, sort: 'ascending' })
    assert.deepEqual(result.values, ['-0.02', '-0.01', '0.00', '0.01', '0.02'])
    assert.match(result.rule, /不重复/)
  })

  it('handles 1000 unique values without collision-based retry loops', () => {
    const result = generateRandomNumbers({ ...defaults, min: '1', max: '1000', count: 1000, allowDuplicates: false, sort: 'descending' })
    assert.equal(new Set(result.values).size, 1000)
    assert.equal(result.values[0], '1000')
    assert.equal(result.values[999], '1')
  })

  it('allows a constant range only when its capacity satisfies the request', () => {
    assert.deepEqual(generateRandomNumbers({ ...defaults, min: '3', max: '3', count: 3 }).values, ['3', '3', '3'])
    assert.throws(() => generateRandomNumbers({ ...defaults, min: '3', max: '3', count: 2, allowDuplicates: false }), /不足/)
  })

  it('rejects endpoints that cannot be represented at the selected precision', () => {
    assert.throws(() => generateRandomNumbers({ ...defaults, min: '0.001', kind: 'decimal', precision: 2 }), /精度/)
    assert.throws(() => generateRandomNumbers({ ...defaults, min: '1.5' }), /整数/)
    assert.throws(() => generateRandomNumbers({ ...defaults, min: '9007199254740992' }), /范围过大/)
  })

  it('rejects invalid or excessive options before sampling', () => {
    for (const options of [{ min: 'Infinity' }, { min: '11' }, { count: 0 }, { count: 1001 }, { count: 1.5 }, { kind: 'decimal' as const, precision: 9 }]) {
      assert.throws(() => generateRandomNumbers({ ...defaults, ...options }))
    }
  })

  it('rejects excess random values instead of applying biased modulo reduction', () => {
    let draws = 0
    const result = generateRandomNumbers({ ...defaults, min: '0', max: '2', count: 1 }, array => {
      array.fill(draws++ === 0 ? 0xffffffff : 0)
    })
    assert.deepEqual(result.values, ['0'])
    assert.equal(draws, 2)
  })

  it('bounds retries when an entropy source keeps returning rejected values', () => {
    assert.throws(() => generateRandomNumbers({ ...defaults, min: '0', max: '2', count: 1 }, array => { array.fill(0xffffffff) }), /随机/)
  })
})
