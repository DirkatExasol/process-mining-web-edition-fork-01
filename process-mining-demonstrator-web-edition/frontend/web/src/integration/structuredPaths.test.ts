/** structuredPaths — client-side JSON/XML path resolvers (mirror of backend structured.py). */

import { describe, expect, it } from 'vitest'
import {
  flattenJson,
  flattenXml,
  jsonPath,
  parseXml,
  resolveFieldValue,
  sampleLeaves,
  scalar,
  xmlValue,
} from './structuredPaths'

describe('jsonPath', () => {
  const obj = { user: { id: 7 }, items: [{ sku: 'A' }, { sku: 'B' }], 'weird.key': 9 }

  it('resolves dot and bracket paths', () => {
    expect(jsonPath(obj, 'user.id')).toBe(7)
    expect(jsonPath(obj, 'items[1].sku')).toBe('B')
    expect(jsonPath(obj, 'items[-1].sku')).toBe('B')
    expect(jsonPath(obj, '["weird.key"]')).toBe(9)
    expect(jsonPath(obj, '$.user.id')).toBe(7)
  })

  it('returns undefined for a missing / out-of-range / wrong-type path', () => {
    expect(jsonPath(obj, 'user.missing')).toBeUndefined()
    expect(jsonPath(obj, 'items[9].sku')).toBeUndefined()
    expect(jsonPath(obj, 'user.id.deeper')).toBeUndefined()
  })
})

describe('scalar', () => {
  it('renders single values, null for containers', () => {
    expect(scalar(true)).toBe('true')
    expect(scalar(3)).toBe('3')
    expect(scalar('x')).toBe('x')
    expect(scalar({ a: 1 })).toBeNull()
    expect(scalar([1])).toBeNull()
    expect(scalar(null)).toBeNull()
  })
})

describe('xmlValue', () => {
  const el = parseXml('<event id="1"><user name="ann"/><step>login</step></event>')!

  it('resolves attributes and child text', () => {
    expect(xmlValue(el, '@id')).toBe('1')
    expect(xmlValue(el, 'step')).toBe('login')
    expect(xmlValue(el, 'user@name')).toBe('ann')
    expect(xmlValue(el, 'missing')).toBeNull()
    expect(xmlValue(el, 'user@missing')).toBeNull()
  })
})

describe('flatten', () => {
  it('flattens JSON leaves with paths', () => {
    const leaves = flattenJson({ user: { id: 7 }, items: [{ sku: 'A' }] })
    expect(leaves).toContainEqual({ path: 'user.id', value: '7' })
    expect(leaves).toContainEqual({ path: 'items[0].sku', value: 'A' })
  })

  it('flattens XML attributes and child texts', () => {
    const el = parseXml('<event id="1"><step>login</step></event>')!
    const leaves = flattenXml(el)
    expect(leaves).toContainEqual({ path: '@id', value: '1' })
    expect(leaves).toContainEqual({ path: 'step', value: 'login' })
  })
})

describe('resolveFieldValue / sampleLeaves', () => {
  it('resolves against a sample record by format', () => {
    expect(resolveFieldValue('json', '{"a":{"b":5}}', 'a.b')).toBe('5')
    expect(resolveFieldValue('xml', '<r x="9"/>', '@x')).toBe('9')
    expect(resolveFieldValue('json', 'not json', 'a')).toBeNull()
    expect(resolveFieldValue('text', 'anything', 'a')).toBeNull()
  })

  it('lists sample leaves by format', () => {
    expect(sampleLeaves('json', '{"a":1}')).toContainEqual({ path: 'a', value: '1' })
    expect(sampleLeaves('xml', '<r a="1"/>')).toContainEqual({ path: '@a', value: '1' })
    expect(sampleLeaves('json', 'broken')).toEqual([])
  })
})
