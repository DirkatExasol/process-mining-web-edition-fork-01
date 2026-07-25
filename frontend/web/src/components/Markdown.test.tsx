import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Markdown } from './Markdown'

describe('Markdown raw-HTML sanitization', () => {
  it('strips scripts and event handlers from LLM-produced HTML blocks', () => {
    const evil = '<div onclick="steal()"><img src=x onerror="alert(document.cookie)"><script>alert(1)</script>ok</div>'
    const { container } = render(<Markdown text={evil} />)
    const html = container.innerHTML
    expect(html).not.toContain('onerror')
    expect(html).not.toContain('onclick')
    expect(html.toLowerCase()).not.toContain('<script')
    expect(html).toContain('ok')            // benign content survives
  })

  it('keeps safe formatting tags (table/div)', () => {
    const { container } = render(<Markdown text={'<table><tr><td>cell</td></tr></table>'} />)
    expect(container.querySelector('table')).not.toBeNull()
    expect(container.textContent).toContain('cell')
  })
})
