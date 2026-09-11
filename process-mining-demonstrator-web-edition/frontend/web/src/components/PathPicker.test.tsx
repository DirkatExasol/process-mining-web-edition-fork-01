/** JsonPathPicker / XmlPathPicker — click a sample record's field to assign its path. */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { JsonPathPicker } from './JsonPathPicker'
import { XmlPathPicker } from './XmlPathPicker'

describe('JsonPathPicker', () => {
  it('lists the sample record leaves and assigns a path on click', () => {
    const onPick = vi.fn()
    render(
      <JsonPathPicker
        sample={'{"user":{"id":7},"step":"login"}'}
        onPick={onPick}
        color="#000"
      />,
    )
    // The leaves are shown as their path selectors.
    expect(screen.getByText('user.id')).toBeTruthy()
    fireEvent.click(screen.getByText('step'))
    expect(onPick).toHaveBeenCalledWith('step')
  })
})

describe('XmlPathPicker', () => {
  it('shows a record-element input and assigns element/attribute paths', () => {
    const onPick = vi.fn()
    const onRecordPath = vi.fn()
    render(
      <XmlPathPicker
        sample={'<event id="1"><step>login</step></event>'}
        recordPath="event"
        onRecordPath={onRecordPath}
        onPick={onPick}
        color="#000"
      />,
    )
    expect(screen.getByText('@id')).toBeTruthy()
    fireEvent.click(screen.getByText('step'))
    expect(onPick).toHaveBeenCalledWith('step')

    fireEvent.change(screen.getByDisplayValue('event'), { target: { value: 'record' } })
    expect(onRecordPath).toHaveBeenCalledWith('record')
  })
})
