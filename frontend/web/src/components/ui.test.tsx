/** Component render smoke tests — the web analogue of the Swift UI launch tests.
 *  They confirm the React + jsdom pipeline mounts the shared primitives and that
 *  the Markdown renderer produces the expected structure. */

import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { RangeSlider, Segmented, Switch, Unavailable } from './ui'
import { Markdown } from './Markdown'

describe('Unavailable', () => {
  it('renders a title and description', () => {
    render(<Unavailable glyph="🗺" title="No Project" description="Pick one." />)
    expect(screen.getByText('No Project')).toBeInTheDocument()
    expect(screen.getByText('Pick one.')).toBeInTheDocument()
  })
})

describe('Switch', () => {
  it('toggles on click', () => {
    let value = false
    const { rerender } = render(<Switch checked={value} onChange={(v) => (value = v)} />)
    fireEvent.click(screen.getByRole('switch'))
    expect(value).toBe(true)
    rerender(<Switch checked={value} onChange={(v) => (value = v)} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })
})

describe('Segmented', () => {
  it('reports the selected value', () => {
    let selected = 'a'
    render(
      <Segmented
        options={[
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ]}
        value={selected}
        onChange={(v) => (selected = v)}
      />,
    )
    fireEvent.click(screen.getByText('B'))
    expect(selected).toBe('b')
  })
})

describe('RangeSlider', () => {
  it('renders both thumbs and the formatted bounds', () => {
    render(
      <RangeSlider
        min={0}
        max={100}
        low={20}
        high={80}
        onChange={() => undefined}
        format={(v) => `${v}%`}
      />,
    )
    expect(screen.getByText('20%')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getAllByRole('slider')).toHaveLength(2)
  })
})

describe('Markdown', () => {
  it('renders headings, bold spans and tables', () => {
    const { container } = render(
      <Markdown
        text={'# Title\n\nSome **bold** text.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n'}
      />,
    )
    expect(container.querySelector('h1')?.textContent).toBe('Title')
    expect(container.querySelector('strong')?.textContent).toBe('bold')
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(table?.querySelectorAll('thead th')).toHaveLength(2)
    expect(table?.querySelectorAll('tbody tr')).toHaveLength(1)
  })

  it('renders bullet lists', () => {
    const { container } = render(<Markdown text={'- one\n- two\n- three'} />)
    expect(container.querySelectorAll('ul li')).toHaveLength(3)
  })
})
