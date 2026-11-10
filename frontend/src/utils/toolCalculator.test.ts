import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { calculateExpression, formatCalculatorResult } from './tools/calculator'

describe('calculator tool', () => {
  it('applies multiplication before addition and respects parentheses', () => {
    assert.equal(calculateExpression('2 + 3 * 4'), 14)
    assert.equal(calculateExpression('(2 + 3) * 4'), 20)
    assert.equal(calculateExpression('20 / 5 * 2 - 3'), 5)
  })

  it('supports unary signs, decimal values, and scientific notation', () => {
    assert.equal(calculateExpression('-(2 + 3) * -2 + .5'), 10.5)
    assert.equal(calculateExpression('2 * --3'), 6)
    assert.equal(calculateExpression('1e3 + 2.5e-1'), 1000.25)
  })

  it('defines percent as remainder with the dividend sign', () => {
    assert.equal(calculateExpression('10 % 3'), 1)
    assert.equal(calculateExpression('-10 % 3'), -1)
    assert.equal(calculateExpression('5 + 8 % 3 * 2'), 9)
  })

  it('rejects division by zero, overflow, and malformed expressions', () => {
    for (const expression of ['1 / 0', '1 % 0', '1e309', '1e308 * 10', '(1 + 2', '1 + 2)', '2(3)', '1..2', '2 +', '', '*3']) {
      assert.throws(() => calculateExpression(expression), Error, expression)
    }
  })

  it('rejects JavaScript and unknown tokens without executing input', () => {
    for (const expression of ['globalThis.process.exit()', 'Math.sqrt(4)', '2 ** 3', '2; 3', '1,2', '0x10']) {
      assert.throws(() => calculateExpression(expression), Error, expression)
    }
  })

  it('rejects excessive size and nesting before exhausting resources', () => {
    assert.throws(() => calculateExpression('1+'.repeat(600) + '1'), /过长/)
    assert.throws(() => calculateExpression('('.repeat(70) + '1' + ')'.repeat(70)), /层级/)
  })

  it('formats common floating point artifacts and negative zero for display', () => {
    assert.equal(formatCalculatorResult(calculateExpression('0.1 + 0.2')), '0.3')
    assert.equal(formatCalculatorResult(calculateExpression('1 / 3')), '0.333333333333333')
    assert.equal(formatCalculatorResult(-0), '0')
  })
})
