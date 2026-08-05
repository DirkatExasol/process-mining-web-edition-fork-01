/** Pure helpers for the source-type wizard: run a field's regex against the pasted
 *  sample (client-side, so arbitrary user regexes never reach the server) and build a
 *  non-overlapping, role-coloured highlight of the sample. */

export type FieldRole = 'timestamp' | 'id' | 'step' | 'meta'

export interface ExtractionField {
  id?: string
  name: string
  role: FieldRole
  regex: string
  format?: string
  /** Business name for a meta field (→ METAS.META_n_TITLE). */
  title?: string
}

/** One match of a field regex: the captured value and its char span in the sample.
 *  When the regex has a capturing group, the span/value is that of group 1; otherwise
 *  it's the whole match. */
export interface RegexMatch {
  value: string
  start: number
  end: number
}

/** Run `pattern` against `sample`. Returns null when the pattern is invalid, an empty
 *  array when it simply doesn't match. Group 1 is preferred (our stored regexes always
 *  capture the value in group 1). Capped to avoid pathological loops. */
export function matchAll(sample: string, pattern: string): RegexMatch[] | null {
  if (!pattern) return []
  let re: RegExp
  try {
    re = new RegExp(pattern, 'g')
  } catch {
    return null // invalid regex
  }
  const out: RegexMatch[] = []
  let m: RegExpExecArray | null
  let guard = 0
  while ((m = re.exec(sample)) !== null) {
    const whole = m[0]
    const group = m[1]
    let start = m.index
    let value = whole
    if (group !== undefined) {
      const rel = whole.indexOf(group)
      start = m.index + (rel >= 0 ? rel : 0)
      value = group
    }
    out.push({ value, start, end: start + value.length })
    if (m.index === re.lastIndex) re.lastIndex++ // zero-width match — advance
    if (++guard > 10000) break
  }
  return out
}

/** True when `pattern` compiles and matches the sample at least once. */
export function testPattern(sample: string, pattern: string): { ok: boolean; value?: string; error?: boolean } {
  const matches = matchAll(sample, pattern)
  if (matches === null) return { ok: false, error: true }
  if (matches.length === 0) return { ok: false }
  return { ok: true, value: matches[0].value }
}

export interface HighlightSpan {
  text: string
  role: FieldRole | null // null = unhighlighted
}

/** Split `sample` into consecutive spans, painting the first match of each field by
 *  role. Overlaps are resolved first-come (fields earlier in the list win their span). */
export function buildHighlights(sample: string, fields: ExtractionField[]): HighlightSpan[] {
  const claimed: { start: number; end: number; role: FieldRole }[] = []
  for (const f of fields) {
    const matches = matchAll(sample, f.regex)
    if (!matches || matches.length === 0) continue
    for (const mt of matches) {
      if (mt.end <= mt.start) continue
      const overlaps = claimed.some((c) => mt.start < c.end && mt.end > c.start)
      if (!overlaps) claimed.push({ start: mt.start, end: mt.end, role: f.role })
    }
  }
  claimed.sort((a, b) => a.start - b.start)

  const spans: HighlightSpan[] = []
  let cursor = 0
  for (const c of claimed) {
    if (c.start > cursor) spans.push({ text: sample.slice(cursor, c.start), role: null })
    spans.push({ text: sample.slice(c.start, c.end), role: c.role })
    cursor = c.end
  }
  if (cursor < sample.length) spans.push({ text: sample.slice(cursor), role: null })
  return spans
}

export const ROLE_COLOR: Record<FieldRole, string> = {
  timestamp: 'var(--accent)',
  id: '#bf5af2',
  step: 'var(--green)',
  meta: 'var(--orange)',
}

export const ROLE_LABEL: Record<FieldRole, string> = {
  timestamp: 'EVENT_TIME',
  id: 'EVENT_ID',
  step: 'STEP',
  meta: 'Meta',
}

/** Map the current text selection *inside* `container` to character offsets in the
 *  container's text (which equals the sample, since highlight spans preserve it in
 *  order). Returns null when there's no non-empty selection inside the container. */
export function selectionOffsetsWithin(container: HTMLElement): [number, number] | null {
  const sel = typeof window !== 'undefined' ? window.getSelection() : null
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null
  const range = sel.getRangeAt(0)
  if (!container.contains(range.commonAncestorContainer)) return null
  const pre = range.cloneRange()
  pre.selectNodeContents(container)
  pre.setEnd(range.startContainer, range.startOffset)
  const start = pre.toString().length
  const len = range.toString().length
  if (len === 0) return null
  return [start, start + len]
}
