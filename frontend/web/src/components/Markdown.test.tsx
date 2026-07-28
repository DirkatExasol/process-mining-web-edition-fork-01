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

describe('Markdown inline-link href sanitization', () => {
  it('neutralises javascript: and data: links (e.g. note text in a report table)', () => {
    const text = 'row [click](javascript:alert(document.cookie)) and [x](data:text/html,<script>1</script>)'
    const { container } = render(<Markdown text={text} />)
    const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'))
    expect(hrefs.length).toBe(2)
    for (const href of hrefs) {
      expect(href).toBe('#')
      expect(href?.toLowerCase()).not.toContain('javascript')
      expect(href?.toLowerCase()).not.toContain('data:')
    }
  })

  it('keeps http(s), mailto and relative links intact', () => {
    const { container } = render(
      <Markdown text={'[a](https://example.com) [b](mailto:x@y.z) [c](/help) [d](#top)'} />,
    )
    const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['https://example.com', 'mailto:x@y.z', '/help', '#top'])
  })

  it('neutralises protocol-relative links (off-site navigation)', () => {
    const { container } = render(<Markdown text={'[a](//evil.com) [b](/\\evil.com)'} />)
    const hrefs = [...container.querySelectorAll('a')].map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['#', '#'])
  })
})
