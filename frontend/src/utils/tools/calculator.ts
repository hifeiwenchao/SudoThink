type Operator = '+' | '-' | '*' | '/' | '%' | 'u+' | 'u-' | '('

const precedence: Record<Operator, number> = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2, 'u+': 3, 'u-': 3, '(': 0 }

export function calculateExpression(expression: string): number {
  if (expression.length > 1024) throw new Error('表达式过长，最多输入 1024 个字符')
  if (!expression.trim()) throw new Error('请输入数学表达式')
  const numbers: number[] = []
  const operators: Operator[] = []
  let expectValue = true
  let depth = 0

  function applyOperator() {
    const operator = operators.pop()
    if (!operator || operator === '(') throw new Error('括号不匹配')
    const right = numbers.pop()
    if (right === undefined) throw new Error('运算符缺少数值')
    let result: number
    if (operator === 'u+' || operator === 'u-') {
      result = operator === 'u-' ? -right : right
    } else {
      const left = numbers.pop()
      if (left === undefined) throw new Error('运算符缺少数值')
      if ((operator === '/' || operator === '%') && right === 0) throw new Error('除数不能为 0')
      switch (operator) {
        case '+': result = left + right; break
        case '-': result = left - right; break
        case '*': result = left * right; break
        case '/': result = left / right; break
        case '%': result = left % right; break
      }
    }
    if (!Number.isFinite(result)) throw new Error('计算结果超出有限数值范围')
    numbers.push(result)
  }

  for (let index = 0; index < expression.length;) {
    const character = expression[index]
    if (/\s/.test(character)) { index++; continue }
    if (/[\d.]/.test(character)) {
      if (!expectValue) throw new Error(`第 ${index + 1} 个字符前缺少运算符`)
      const match = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(expression.slice(index))
      if (!match) throw new Error(`第 ${index + 1} 个字符不是有效数值`)
      const value = Number(match[0])
      if (!Number.isFinite(value)) throw new Error('数值超出有限范围')
      numbers.push(value)
      expectValue = false
      index += match[0].length
      continue
    }
    if (character === '(') {
      if (!expectValue) throw new Error('左括号前缺少运算符')
      if (++depth > 64) throw new Error('括号层级过深，最多支持 64 层')
      operators.push('(')
    } else if (character === ')') {
      if (expectValue || depth === 0) throw new Error('括号不匹配或括号内缺少数值')
      while (operators.at(-1) !== '(') applyOperator()
      operators.pop()
      depth--
      expectValue = false
    } else if (['+', '-', '*', '/', '%'].includes(character)) {
      if (expectValue) {
        if (character !== '+' && character !== '-') throw new Error('运算符前缺少数值')
        operators.push(character === '+' ? 'u+' : 'u-')
      } else {
        const operator = character as Operator
        while (operators.length && operators.at(-1) !== '(' && precedence[operators.at(-1)!] >= precedence[operator]) applyOperator()
        operators.push(operator)
        expectValue = true
      }
    } else {
      throw new Error(`第 ${index + 1} 个字符不受支持：${character}`)
    }
    index++
  }
  if (expectValue) throw new Error('表达式末尾缺少数值')
  if (depth !== 0) throw new Error('括号不匹配')
  while (operators.length) applyOperator()
  if (numbers.length !== 1) throw new Error('表达式格式有误')
  return numbers[0]
}

export function formatCalculatorResult(value: number): string {
  if (!Number.isFinite(value)) throw new Error('计算结果超出有限数值范围')
  return Number(value.toPrecision(15)).toString()
}
