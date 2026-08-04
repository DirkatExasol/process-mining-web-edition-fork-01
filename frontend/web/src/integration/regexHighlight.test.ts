import { describe, expect, it } from 'vitest'
import { buildHighlights, matchAll, testPattern, type ExtractionField } from './regexHighlight'

const SAMPLE = '2026-08-03 INFO OrderReceived id=42'

describe('matchAll', () => {
  it('captures group 1 with its span', () => {
    const m = matchAll(SAMPLE, '(\\d{4}-\\d{2}-\\d{2})')
    expect(m).not.toBeNull()
    expect(m).toEqual([{ value: '2026-08-03', start: 0, end: 10 }])
  })

  it('returns null for an invalid regex (no throw)', () => {
    expect(matchAll(SAMPLE, '(')).toBeNull()
  })

  it('returns an empty array when nothing matches', () => {
    expect(matchAll(SAMPLE, '(zzz)')).toEqual([])
  })

  it('does not hang on a zero-width pattern', () => {
    const m = matchAll('abc', '(x*)')
    expect(Array.isArray(m)).toBe(true)
  })
})

describe('testPattern', () => {
  it('reports ok + value, no-match, and invalid distinctly', () => {
    expect(testPattern(SAMPLE, '(\\d{4})')).toEqual({ ok: true, value: '2026' })
    expect(testPattern(SAMPLE, '(zzz)')).toEqual({ ok: false })
    expect(testPattern(SAMPLE, '(')).toEqual({ ok: false, error: true })
  })
})

describe('buildHighlights', () => {
  it('paints non-overlapping matches by role and preserves the full text', () => {
    const fields: ExtractionField[] = [
      { name: 'timestamp', role: 'timestamp', regex: '(\\d{4}-\\d{2}-\\d{2})' },
      { name: 'id', role: 'meta', regex: 'id=(\\d+)' },
    ]
    const spans = buildHighlights(SAMPLE, fields)
    expect(spans.map((s) => s.text).join('')).toBe(SAMPLE)
    const painted = spans.filter((s) => s.role)
    expect(painted.map((s) => s.text)).toEqual(['2026-08-03', '42'])
    expect(painted[0].role).toBe('timestamp')
    expect(painted[1].role).toBe('meta')
  })

  it('skips a field whose regex is invalid', () => {
    const spans = buildHighlights(SAMPLE, [{ name: 'x', role: 'meta', regex: '(' }])
    expect(spans).toEqual([{ text: SAMPLE, role: null }])
  })
})
