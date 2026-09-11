/** Colour-helper tests — the port of Color.named / EdgeColorSchema / groupColor. */

import { describe, expect, it } from 'vitest'
import {
  ACCENT,
  EDGE_COLOR_SCHEMAS,
  EDGE_SCHEMA_GRADIENTS,
  defaultSchemaFor,
  groupColor,
  interpolate,
  namedColor,
  rgbToHex,
} from './colors'

describe('namedColor', () => {
  it('resolves named system colours', () => {
    expect(namedColor('blue')).toBe('#007AFF')
    expect(namedColor('GREEN')).toBe('#34C759')
    expect(namedColor('grey')).toBe(namedColor('gray'))
  })

  it('parses 6-digit hex, case-insensitively', () => {
    expect(namedColor('1a2b3c')).toBe('#1A2B3C')
    expect(namedColor('#FF8000')).toBe('#FF8000')
  })

  it('falls back to the accent colour for unknown input', () => {
    expect(namedColor('not-a-colour')).toBe(ACCENT)
    expect(namedColor('')).toBe(ACCENT)
  })
})

describe('interpolate', () => {
  it('returns the endpoints at t=0 and t=1', () => {
    expect(interpolate('#000000', '#FFFFFF', 0)).toBe('#000000')
    expect(interpolate('#000000', '#FFFFFF', 1)).toBe('#FFFFFF')
  })

  it('returns the midpoint at t=0.5', () => {
    expect(interpolate('#000000', '#FFFFFF', 0.5)).toBe(rgbToHex({ r: 128, g: 128, b: 128 }))
  })

  it('clamps out-of-range t', () => {
    expect(interpolate('#000000', '#FFFFFF', -1)).toBe('#000000')
    expect(interpolate('#000000', '#FFFFFF', 2)).toBe('#FFFFFF')
  })
})

describe('groupColor', () => {
  it('is deterministic and returns a hex colour', () => {
    expect(groupColor('Payment')).toBe(groupColor('Payment'))
    expect(groupColor('Payment')).toMatch(/^#[0-9A-F]{6}$/)
  })

  it('gives different groups different hues (usually)', () => {
    expect(groupColor('Payment')).not.toBe(groupColor('Fulfilment'))
  })
})

describe('EdgeColorSchema', () => {
  it('maps each metric to its default schema', () => {
    expect(defaultSchemaFor('Count')).toBe('greenHigh')
    expect(defaultSchemaFor('Avg Time')).toBe('orangeScale')
    expect(defaultSchemaFor('Min Time')).toBe('blueScale')
    expect(defaultSchemaFor('Max Time')).toBe('redHigh')
    expect(defaultSchemaFor('Std Dev')).toBe('purpleScale')
  })

  it('defines a gradient for every schema except neutral', () => {
    for (const schema of EDGE_COLOR_SCHEMAS) {
      const gradient = EDGE_SCHEMA_GRADIENTS[schema]
      if (schema === 'neutral') {
        expect(gradient).toBeNull()
      } else {
        expect(gradient).not.toBeNull()
        expect(gradient?.low).toMatch(/^#[0-9A-F]{6}$/)
        expect(gradient?.high).toMatch(/^#[0-9A-F]{6}$/)
      }
    }
  })
})
