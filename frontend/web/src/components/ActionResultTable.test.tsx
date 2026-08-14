import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ActionResultTable } from './ActionResultTable'
import type { ActionRunResult } from '../actions/types'

afterEach(cleanup)

describe('ActionResultTable', () => {
  it('renders columns and rows, showing — for null cells', () => {
    const result: ActionRunResult = {
      kind: 'logEntries',
      columns: ['EVENT_ID', 'STEP', 'META_1'],
      rows: [
        ['e1', 'PAYMENT', 'x'],
        ['e2', 'LOGIN', null],
      ],
    }
    render(<ActionResultTable result={result} />)
    expect(screen.getByText('EVENT_ID')).toBeTruthy()
    expect(screen.getByText('PAYMENT')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy() // null cell rendered as em dash
  })

  it('shows an empty-state message when there are no rows', () => {
    const result: ActionRunResult = { kind: 'transitionTable', columns: ['FROM', 'TO'], rows: [] }
    render(<ActionResultTable result={result} />)
    expect(screen.getByText(/No rows matched/i)).toBeTruthy()
  })
})
