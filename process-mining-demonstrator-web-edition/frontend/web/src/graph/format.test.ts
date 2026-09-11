/** Formatting-helper tests — ports of the Swift view formatters. */

import { describe, expect, it } from 'vitest'
import {
  formatCount,
  formatDuration,
  formatSecs,
  fromISODate,
  toISODate,
} from './format'

describe('formatCount', () => {
  it('formats plain, thousands and millions', () => {
    expect(formatCount(0)).toBe('0')
    expect(formatCount(999)).toBe('999')
    expect(formatCount(1500)).toBe('1.5k')
    expect(formatCount(2_500_000)).toBe('2.5M')
  })
})

describe('formatDuration', () => {
  it('scales to s / m / h / d', () => {
    expect(formatDuration(45)).toBe('45s')
    expect(formatDuration(120)).toBe('2m')
    expect(formatDuration(5400)).toBe('1.5h')
    expect(formatDuration(172800)).toBe('2.0d')
  })
})

describe('formatSecs', () => {
  it('renders compound units', () => {
    expect(formatSecs(45)).toBe('45s')
    expect(formatSecs(90)).toBe('1m 30s')
    expect(formatSecs(3661)).toBe('1h 1m')
    expect(formatSecs(90000)).toBe('1d 1h')
  })
})

describe('ISO date helpers', () => {
  it('round-trips a date through yyyy-MM-dd', () => {
    const iso = '2024-06-07'
    const date = fromISODate(iso)
    expect(date).not.toBeNull()
    expect(toISODate(date as Date)).toBe(iso)
  })

  it('returns empty / null for invalid input', () => {
    expect(toISODate(null)).toBe('')
    expect(fromISODate('')).toBeNull()
  })
})
