import { describe, expect, it } from 'vitest'
import { loginBackground } from './loginAppearance'

describe('loginBackground', () => {
  it('falls back to the theme colour for default / null / bad input', () => {
    expect(loginBackground(null)).toBe('var(--bg-grouped)')
    expect(loginBackground({ type: 'default', color: '', image: '' })).toBe(
      'var(--bg-grouped)',
    )
    // a color type without a valid hex must not leak into CSS
    expect(loginBackground({ type: 'color', color: 'red', image: '' })).toBe(
      'var(--bg-grouped)',
    )
    // an image type without a data: URI is ignored
    expect(loginBackground({ type: 'image', color: '', image: 'http://x/y.png' })).toBe(
      'var(--bg-grouped)',
    )
    // an image whose payload isn't pure base64 (could break out of url("…") and
    // inject an external layer) is rejected — only the strict data URI is used
    expect(
      loginBackground({
        type: 'image',
        color: '',
        image: 'data:image/png;base64,abc"),url(http://evil/beacon',
      }),
    ).toBe('var(--bg-grouped)')
  })

  it('uses a valid hex colour', () => {
    expect(loginBackground({ type: 'color', color: '#0A84FF', image: '' })).toBe(
      '#0A84FF',
    )
  })

  it('layers a data-URI image over the fallback colour', () => {
    const image = 'data:image/png;base64,iVBORw0KGgo='
    expect(loginBackground({ type: 'image', color: '', image })).toBe(
      `var(--bg-grouped) url("${image}") center / cover no-repeat`,
    )
  })

  it('honours a custom fallback', () => {
    expect(loginBackground(null, 'var(--l-grouped)')).toBe('var(--l-grouped)')
  })
})
