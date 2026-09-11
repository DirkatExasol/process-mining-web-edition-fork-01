/** Client-side JSON / XML path resolvers for the source-type wizard — the semi-structured
 *  counterpart to regexHighlight.ts. They mirror the backend's `structured.py` so the
 *  wizard can show the value a path selector would extract, and flatten a sample record
 *  into a list of pickable leaves. Pure + dependency-free (JSON via `JSON.parse`, XML via
 *  the browser's `DOMParser`); user paths are walked structurally, never `eval`'d. */

import type { DataFormat } from '../types'

// ── JSON key paths (a.b[0].c) ────────────────────────────────────────────────

const PLAIN_KEY = /^[A-Za-z_][A-Za-z0-9_-]*$/

function jsonTokens(path: string): (string | number)[] {
  let p = path.trim()
  if (p.startsWith('$')) p = p.slice(1)
  const toks: (string | number)[] = []
  let pos = 0
  while (pos < p.length) {
    const c = p[pos]
    if (c === '.') {
      pos++
      continue
    }
    if (c === '[') {
      const end = p.indexOf(']', pos)
      if (end === -1) throw new Error('unbalanced [')
      const inner = p.slice(pos + 1, end).trim()
      if (inner.length >= 2 && (inner[0] === '"' || inner[0] === "'") && inner[inner.length - 1] === inner[0]) {
        toks.push(inner.slice(1, -1))
      } else {
        const n = Number(inner)
        if (!Number.isInteger(n)) throw new Error('bad index')
        toks.push(n)
      }
      pos = end + 1
    } else {
      let j = pos
      while (j < p.length && p[j] !== '.' && p[j] !== '[') j++
      toks.push(p.slice(pos, j))
      pos = j
    }
  }
  return toks
}

export function jsonPath(obj: unknown, path: string): unknown {
  const stripped = path.trim().replace(/^\$/, '')
  if (stripped === '' || stripped === '.') return obj
  let toks: (string | number)[]
  try {
    toks = jsonTokens(path)
  } catch {
    return undefined
  }
  let cur: unknown = obj
  for (const t of toks) {
    if (typeof t === 'number') {
      if (Array.isArray(cur)) {
        const idx = t < 0 ? cur.length + t : t
        if (idx < 0 || idx >= cur.length) return undefined
        cur = cur[idx]
      } else return undefined
    } else {
      if (cur && typeof cur === 'object' && !Array.isArray(cur) && t in (cur as Record<string, unknown>)) {
        cur = (cur as Record<string, unknown>)[t]
      } else return undefined
    }
  }
  return cur
}

/** Render a resolved value as the string the extractor would store; null for a container
 *  (a path that landed on an object/array) or a missing value. */
export function scalar(value: unknown): string | null {
  if (value === null || value === undefined || typeof value === 'object') return null
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function joinJson(prefix: string, key: string): string {
  if (PLAIN_KEY.test(key)) return prefix ? `${prefix}.${key}` : key
  const token = `[${JSON.stringify(key)}]`
  return prefix ? `${prefix}${token}` : token
}

export interface Leaf {
  path: string
  value: string
}

export function flattenJson(obj: unknown, prefix = '', out: Leaf[] = [], depth = 0): Leaf[] {
  if (depth > 6) return out
  if (Array.isArray(obj)) {
    obj.forEach((v, i) => flattenJson(v, `${prefix}[${i}]`, out, depth + 1))
  } else if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      flattenJson(v, joinJson(prefix, k), out, depth + 1)
    }
  } else {
    out.push({ path: prefix || '$', value: obj === null ? 'null' : String(obj) })
  }
  return out
}

// ── XML element/attribute paths (a/b@attr) ───────────────────────────────────

export function parseXml(text: string): Element | null {
  try {
    const doc = new DOMParser().parseFromString(text, 'application/xml')
    if (doc.getElementsByTagName('parsererror').length > 0) return null
    return doc.documentElement
  } catch {
    return null
  }
}

function localName(el: Element): string {
  return el.localName || el.tagName.split(':').pop() || el.tagName
}

function childByTag(el: Element, tag: string): Element | null {
  for (const c of Array.from(el.children)) if (localName(c) === tag) return c
  return null
}

function findByPath(el: Element, path: string): Element | null {
  const parts = path.split('/').filter((p) => p && p !== '.')
  let cur: Element | null = el
  for (const part of parts) {
    if (!cur) return null
    cur = childByTag(cur, part)
  }
  return cur
}

function directText(el: Element): string {
  let s = ''
  for (const n of Array.from(el.childNodes)) if (n.nodeType === 3) s += n.textContent ?? ''
  return s
}

export function xmlValue(el: Element, spec: string): string | null {
  let s = (spec || '').trim()
  if (!s) return null
  let attr: string | null = null
  const at = s.lastIndexOf('@')
  if (at !== -1) {
    attr = s.slice(at + 1).trim()
    s = s.slice(0, at).trim()
  }
  let target: Element | null = el
  if (s !== '' && s !== '.' && s !== './') {
    target = findByPath(el, s)
    if (!target) return null
  }
  if (attr) return target.getAttribute(attr)
  const t = directText(target).trim()
  return t || null
}

export function flattenXml(el: Element, prefix = '', out: Leaf[] = [], depth = 0, maxDepth = 4): Leaf[] {
  for (const a of Array.from(el.attributes)) {
    out.push({ path: prefix ? `${prefix}@${a.name}` : `@${a.name}`, value: a.value })
  }
  const children = Array.from(el.children)
  const text = directText(el).trim()
  if (text && children.length === 0) out.push({ path: prefix || '.', value: text })
  if (depth < maxDepth) {
    for (const c of children) {
      const cp = prefix ? `${prefix}/${localName(c)}` : localName(c)
      flattenXml(c, cp, out, depth + 1, maxDepth)
    }
  }
  return out
}

// ── format-agnostic helpers the wizard calls ─────────────────────────────────

/** The value a field's path selector extracts from one sample record (or null). */
export function resolveFieldValue(format: DataFormat, sampleRecord: string, path: string): string | null {
  if (!path.trim()) return null
  if (format === 'json') {
    let obj: unknown
    try {
      obj = JSON.parse(sampleRecord)
    } catch {
      return null
    }
    return scalar(jsonPath(obj, path))
  }
  if (format === 'xml') {
    const el = parseXml(sampleRecord)
    return el ? xmlValue(el, path) : null
  }
  return null
}

/** The pickable leaves of one sample record — its scalar JSON leaves, or an XML element's
 *  attributes + child texts — each with the path selector that reaches it. */
export function sampleLeaves(format: DataFormat, sampleRecord: string): Leaf[] {
  if (!sampleRecord.trim()) return []
  if (format === 'json') {
    let obj: unknown
    try {
      obj = JSON.parse(sampleRecord)
    } catch {
      return []
    }
    return flattenJson(obj)
  }
  if (format === 'xml') {
    const el = parseXml(sampleRecord)
    return el ? flattenXml(el) : []
  }
  return []
}
