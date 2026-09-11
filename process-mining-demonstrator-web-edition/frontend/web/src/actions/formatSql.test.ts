import { describe, expect, it } from 'vitest'
import { formatSql } from './formatSql'

describe('formatSql', () => {
  it('breaks a one-line sub-SELECT with JOINs across lines and indents it', () => {
    const raw =
      "SELECT EVENT_ID, STEP FROM JOURNEYS WHERE PROJECT_ID = 'P' " +
      "AND EVENT_ID IN (SELECT j.EVENT_ID FROM JOURNEYS j LEFT JOIN STEPS s " +
      "ON j.STEP = s.STEP AND j.PROJECT_ID = s.PROJECT_ID WHERE PROJECT_ID = 'P' " +
      "GROUP BY j.EVENT_ID HAVING COUNT(*) BETWEEN 1 AND 5) ORDER BY EVENT_TIME DESC LIMIT 5"
    expect(formatSql(raw)).toBe(
      [
        'SELECT EVENT_ID, STEP',
        "FROM JOURNEYS",
        "WHERE PROJECT_ID = 'P'",
        'AND EVENT_ID IN (',
        '  SELECT j.EVENT_ID',
        '  FROM JOURNEYS j',
        '  LEFT JOIN STEPS s',
        '  ON j.STEP = s.STEP',
        '  AND j.PROJECT_ID = s.PROJECT_ID',
        "  WHERE PROJECT_ID = 'P'",
        '  GROUP BY j.EVENT_ID',
        '  HAVING COUNT(*) BETWEEN 1 AND 5',
        ')',
        'ORDER BY EVENT_TIME DESC',
        'LIMIT 5',
      ].join('\n'),
    )
  })

  it('never removes horizontal space between tokens', () => {
    const out = formatSql("WHERE PROJECT_ID = 'x' AND STEP = 'A'")
    expect(out).toContain("PROJECT_ID = 'x'")
    expect(out).toContain("STEP = 'A'")
    expect(out.split('\n')).toEqual(["WHERE PROJECT_ID = 'x'", "AND STEP = 'A'"])
  })

  it('keeps function-call parens inline (no spurious subquery block)', () => {
    const out = formatSql('SELECT COUNT(*) AS CNT, MAX(EVENT_TIME) FROM JOURNEYS')
    expect(out).toBe('SELECT COUNT(*) AS CNT, MAX(EVENT_TIME)\nFROM JOURNEYS')
  })

  it('does not mangle real numbers (no placeholder collision with LIMIT 5)', () => {
    const out = formatSql("WHERE STEP IN ('A', 'B') LIMIT 5")
    expect(out).toContain("STEP IN ('A', 'B')")
    expect(out).toContain('LIMIT 5')
  })

  it('keeps BETWEEN x AND y on one line', () => {
    const out = formatSql('HAVING COUNT(*) BETWEEN 1 AND 5')
    expect(out).toBe('HAVING COUNT(*) BETWEEN 1 AND 5')
  })

  it('preserves commas/parens inside string literals', () => {
    const out = formatSql("WHERE STEP = 'Ship, then (invoice)'")
    expect(out).toBe("WHERE STEP = 'Ship, then (invoice)'")
  })

  it('handles empty input', () => {
    expect(formatSql('')).toBe('')
    expect(formatSql('\n\n')).toBe('')
  })
})
