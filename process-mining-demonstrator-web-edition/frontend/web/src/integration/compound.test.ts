import { describe, expect, it } from 'vitest'
import { deriveCompoundStep } from './regexHighlight'
import type { CompoundRule } from '../types'

const LOGIN: CompoundRule[] = [
  { id: '1', step: 'login successful', when: [
    { field: 'step', op: 'eq', value: 'login' },
    { field: 'status', op: 'eq', value: '200' },
  ] },
  { id: '2', step: 'login failed', when: [
    { field: 'step', op: 'eq', value: 'login' },
    { field: 'status', op: 'eq', value: '500' },
  ] },
]

describe('deriveCompoundStep (mirrors backend compound.py)', () => {
  it('derives the step from two fields', () => {
    expect(deriveCompoundStep(LOGIN, { step: 'login', status: '200' })).toBe('login successful')
    expect(deriveCompoundStep(LOGIN, { step: 'login', status: '500' })).toBe('login failed')
    expect(deriveCompoundStep(LOGIN, { step: 'login', status: '404' })).toBeNull()
    expect(deriveCompoundStep(LOGIN, { step: 'basket', status: '200' })).toBeNull()
  })

  it('requires every condition and takes the first match', () => {
    const rules: CompoundRule[] = [
      { id: 'a', step: 'first', when: [{ field: 'a', op: 'eq', value: '1' }] },
      { id: 'b', step: 'second', when: [
        { field: 'a', op: 'eq', value: '1' }, { field: 'b', op: 'eq', value: '2' },
      ] },
    ]
    expect(deriveCompoundStep(rules, { a: '1', b: '2' })).toBe('first')
    // A missing field never satisfies a condition.
    expect(deriveCompoundStep([rules[1]], { a: '1' })).toBeNull()
  })

  it('supports every operator, case-insensitively', () => {
    const one = (op: CompoundRule['when'][0]['op'], value: string, actual: string) =>
      deriveCompoundStep([{ id: 'x', step: 'hit', when: [{ field: 'f', op, value }] }], { f: actual })
    expect(one('eq', 'LOGIN', 'login')).toBe('hit')
    expect(one('eq', 'login', ' login ')).toBe('hit')
    expect(one('ne', 'logout', 'login')).toBe('hit')
    expect(one('contains', 'gi', 'login')).toBe('hit')
    expect(one('startswith', 'log', 'login')).toBe('hit')
    expect(one('endswith', 'gin', 'login')).toBe('hit')
    expect(one('regex', '^\\d{3}$', '200')).toBe('hit')
    expect(one('regex', '^\\d{3}$', '20x')).toBeNull()
    expect(one('regex', '([', 'anything')).toBeNull()  // invalid pattern never matches
  })

  it('ignores incomplete rules', () => {
    expect(deriveCompoundStep([{ id: 'x', step: 'x', when: [] }], { a: '1' })).toBeNull()
    expect(deriveCompoundStep([{ id: 'x', step: '', when: [{ field: 'a', op: 'eq', value: '1' }] }], { a: '1' })).toBeNull()
    expect(deriveCompoundStep([], { a: '1' })).toBeNull()
  })
})
