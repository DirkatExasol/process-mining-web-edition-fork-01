/** Help panel search — filters the table of contents to matching sections,
 *  navigates to a hit, and highlights matches in the rendered chapter. */

import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { HelpPanel } from './HelpPanel'

describe('HelpPanel search', () => {
  it('shows the full table of contents until a query is entered', () => {
    render(<HelpPanel onClose={() => {}} />)
    // A well-known chapter is listed in the TOC.
    expect(screen.getByRole('button', { name: /Overview/ })).toBeInTheDocument()
    // No result/empty affordances before searching.
    expect(screen.queryByText(/results?$/)).toBeNull()
  })

  it('filters to matching sections and reports a count', () => {
    render(<HelpPanel onClose={() => {}} />)
    const box = screen.getByRole('searchbox', { name: /search help/i })
    fireEvent.change(box, { target: { value: 'MD5' } })

    // A result count appears and at least one result mentions the demo ID chapter.
    expect(screen.getByText(/result/)).toBeInTheDocument()
    expect(screen.getByText('Demo event-ID format')).toBeInTheDocument()
  })

  it('navigates to a result and highlights the query in the chapter', () => {
    render(<HelpPanel onClose={() => {}} />)
    const box = screen.getByRole('searchbox', { name: /search help/i })
    fireEvent.change(box, { target: { value: 'event-ID format' } })

    fireEvent.click(screen.getByRole('button', { name: /Demo event-ID format/ }))

    // The chapter content now renders and the term is wrapped in a <mark>.
    const content = document.querySelector('.help-content') as HTMLElement
    const marks = within(content).getAllByText(/event-ID format/i, {
      selector: 'mark',
    })
    expect(marks.length).toBeGreaterThan(0)
  })

  it('reports when nothing matches', () => {
    render(<HelpPanel onClose={() => {}} />)
    const box = screen.getByRole('searchbox', { name: /search help/i })
    fireEvent.change(box, { target: { value: 'zzzznotarealterm' } })
    expect(screen.getByText(/No matches for/)).toBeInTheDocument()
  })
})
