/** Help panel search — filters the table of contents to matching sections,
 *  navigates to a hit, and highlights matches in the rendered chapter. */

import { afterEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { HelpPanel } from './HelpPanel'
import { useStore } from '../store'
import { resetStoreOutsideRender } from '../test/renderSettled'

// Some tests flip authIsAdmin. Reset it after unmounting, so restoring the default can't
// re-render a still-mounted HelpPanel outside act().
afterEach(() => resetStoreOutsideRender(() => useStore.setState({ authIsAdmin: false })))

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

describe('HelpPanel TOC grouping', () => {
  it('nests Process Goodness and Process Similarity under a Computational Insights group', () => {
    render(<HelpPanel onClose={() => {}} />)
    // The group heading is expanded by default, showing both chapters.
    const group = screen.getByRole('button', { name: /Computational Insights/ })
    expect(group).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: /Process Goodness/ })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /Process Similarity/ }),
    ).toBeInTheDocument()

    // Collapsing the group hides its chapters from the TOC.
    fireEvent.click(group)
    expect(group).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: /Process Goodness/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Process Similarity/ })).toBeNull()
  })
})

describe('HelpPanel Users & Permissions matrix', () => {
  it('renders the capability matrix as a table (visible to non-admins)', () => {
    useStore.setState({ authIsAdmin: false })
    render(<HelpPanel onClose={() => {}} />)
    // A general (non-admin) chapter — a regular user can reach it in the TOC.
    fireEvent.click(screen.getByRole('button', { name: /Users & Permissions/ }))
    const content = document.querySelector('.help-content') as HTMLElement
    const table = content.querySelector('table.help-table') as HTMLTableElement
    expect(table).not.toBeNull()
    expect(within(content).getByText('Capability')).toBeInTheDocument()
    // The sampling row marks Regular unavailable, Power/Admin available.
    const rows = [...table.querySelectorAll('tbody tr')]
    const samplingRow = rows.find((r) => /sampling/i.test(r.textContent || ''))
    expect(samplingRow).toBeDefined()
    const cells = samplingRow!.querySelectorAll('td')
    expect(cells[1].textContent).toBe('—') // Regular
    expect(cells[2].textContent).toBe('✓') // Power
    expect(cells[3].textContent).toBe('✓') // Admin
  })
})

describe('HelpPanel Administration group (admin-only)', () => {
  it('hides the Administration group and its chapters from non-admins', () => {
    useStore.setState({ authIsAdmin: false })
    render(<HelpPanel onClose={() => {}} />)
    expect(screen.queryByRole('button', { name: /Administration/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /TLS \/ SSL/ })).toBeNull()
    expect(screen.queryByRole('button', { name: /Directory \(LDAP\)/ })).toBeNull()
    // Non-admin chapters remain.
    expect(screen.getByRole('button', { name: /Overview/ })).toBeInTheDocument()
  })

  it('shows the Administration group and its chapters to admins', () => {
    useStore.setState({ authIsAdmin: true })
    render(<HelpPanel onClose={() => {}} />)
    const group = screen.getByRole('button', { name: /Administration/ })
    expect(group).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: /TLS \/ SSL/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Directory \(LDAP\)/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Logging/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Customize/ })).toBeInTheDocument()
  })
})
