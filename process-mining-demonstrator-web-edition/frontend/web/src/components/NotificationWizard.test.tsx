/** NotificationWizard — the ruleSummary label plus the "Test now" button that evaluates a
 *  rule against current data without saving. */

import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

const testNotification = vi.fn()
const updateNotification = vi.fn(async (): Promise<unknown> => ({}))
const pushTest = vi.fn(async (): Promise<unknown> => ({ sent: 1, failed: 0, errors: [] }))
vi.mock('../api', () => ({
  api: {
    testNotification: (...a: unknown[]) => testNotification(...(a as [])),
    notificationSteps: vi.fn(async () => ({ steps: ['A', 'B'] })),
    saveNotification: vi.fn(async () => ({})),
    updateNotification: (...a: unknown[]) => updateNotification(...(a as [])),
    deleteNotification: vi.fn(async () => ({})),
    pushTest: () => pushTest(),
  },
}))
// Pretend this browser supports and is subscribed to push, so the remote UI shows fully.
vi.mock('../push', () => ({
  pushSupported: () => true,
  isPushEnabled: async () => true,
  enablePush: async () => {},
  disablePush: async () => {},
}))

import { NotificationWizard, ruleSummary } from './NotificationWizard'
import { renderSettled } from '../test/renderSettled'
import type { DashboardConnection, NotificationRule } from '../types'

const base: NotificationRule = {
  id: 'r', connectionId: 'c', projectId: 1, projectTitle: 'P', kind: 'transition_metric',
  name: '', severity: 'IMPORTANT', intervalSecs: 300, enabled: true,
  config: { fromStep: 'Order', toStep: 'Ship', metric: 'Avg Time', comparator: '>', threshold: 7200 },
  state: {},
}

describe('ruleSummary', () => {
  it('formats a time metric with a human duration threshold', () => {
    expect(ruleSummary(base)).toBe('Avg Time Order → Ship is greater than 2.0h')
  })

  it('formats a count metric with a plain number and the chosen comparator', () => {
    const r: NotificationRule = {
      ...base,
      config: { fromStep: 'A', toStep: 'B', metric: 'Count', comparator: '>=', threshold: 1000 },
    }
    expect(ruleSummary(r)).toBe('Count A → B is at least 1,000')
  })

  it('formats a journey_duration rule without steps', () => {
    const r: NotificationRule = {
      ...base,
      kind: 'journey_duration',
      config: { metric: 'Max Time', comparator: '>', threshold: 7200 },
    }
    expect(ruleSummary(r)).toBe('Journey duration (Max Time) is greater than 2.0h')
  })
})

const GROUPS = [
  {
    id: 'c1', name: 'Prod', schema: 'MINING', error: null,
    projects: [{ projectId: 1, title: 'Bookstore', titleShort: 'BOOK' }],
  },
] as unknown as DashboardConnection[]

const RULE: NotificationRule = {
  ...base, id: 'r1', connectionId: 'c1', projectId: 1, projectTitle: 'Bookstore',
  config: { fromStep: 'A', toStep: 'B', metric: 'Avg Time', comparator: '>', threshold: 7200 },
}

describe('NotificationWizard — Test now', () => {
  it('evaluates the rule against current data and shows the result', async () => {
    testNotification.mockResolvedValue({ ok: true, value: 9000, triggered: true, hasData: true, error: null })
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    // Open the rule for editing (its row shows the summary).
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    // Test it.
    fireEvent.click(await screen.findByText('Test now'))
    await waitFor(() => expect(screen.getByText(/would trigger now/)).toBeTruthy())
    // The measured 9000s is shown as 2.5h, and the threshold went over the wire in seconds.
    expect(screen.getByText(/2\.5h/)).toBeTruthy()
    expect(testNotification).toHaveBeenCalledWith(
      expect.objectContaining({ config: expect.objectContaining({ threshold: 7200 }) }),
    )
  })

  it('saves the Web browser push delivery choice', async () => {
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    // Turn on the remote "Web browser push" channel and save.
    fireEvent.click(await screen.findByText('Web browser push'))
    fireEvent.click(screen.getByText('Save changes'))
    await waitFor(() =>
      expect(updateNotification).toHaveBeenCalledWith(
        RULE.id,
        expect.objectContaining({ delivery: expect.objectContaining({ webpush: true }) }),
      ),
    )
  })

  it('saves Email delivery with recipients', async () => {
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    fireEvent.click(await screen.findByText('Email'))
    fireEvent.change(
      screen.getByPlaceholderText('recipients, comma-separated (optional)'),
      { target: { value: 'ops@team.com, boss@team.com' } },
    )
    fireEvent.click(screen.getByText('Save changes'))
    await waitFor(() =>
      expect(updateNotification).toHaveBeenCalledWith(
        RULE.id,
        expect.objectContaining({
          delivery: expect.objectContaining({
            smtp: { recipients: ['ops@team.com', 'boss@team.com'] },
          }),
        }),
      ),
    )
  })

  it('saves the lookback window', async () => {
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    // Choose a Days window and set the number.
    const lookback = (await screen.findByText('All history')).closest('select') as HTMLSelectElement
    fireEvent.change(lookback, { target: { value: 'days' } })
    fireEvent.change(await screen.findByDisplayValue('7'), { target: { value: '14' } })
    fireEvent.click(screen.getByText('Save changes'))
    await waitFor(() =>
      expect(updateNotification).toHaveBeenCalledWith(
        RULE.id,
        expect.objectContaining({
          config: expect.objectContaining({ lookbackUnit: 'days', lookbackValue: 14 }),
        }),
      ),
    )
  })

  it('sends a test push from the remote section', async () => {
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    fireEvent.click(await screen.findByText('Web browser push')) // reveals the device controls
    fireEvent.click(await screen.findByText('Send a test notification'))
    await waitFor(() => expect(pushTest).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/Sent to 1 device/)).toBeTruthy())
  })

  it('creates a journey_duration rule with no step selection', async () => {
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText('＋ New rule'))
    // Switch the check type to Journey duration — the step pickers disappear.
    const kind = (await screen.findByText('Check type')).closest('label')
      ?.querySelector('select') as HTMLSelectElement
    fireEvent.change(kind, { target: { value: 'journey_duration' } })
    expect(screen.queryByText('From step')).toBeNull()
    // Test now needs no steps for a journey rule.
    testNotification.mockResolvedValue({ ok: true, value: 9000, triggered: true, hasData: true, error: null })
    fireEvent.click(screen.getByText('Test now'))
    await waitFor(() =>
      expect(testNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'journey_duration',
          config: expect.not.objectContaining({ fromStep: expect.anything() }),
        }),
      ),
    )
  })

  it('reports when the transition has no data', async () => {
    testNotification.mockResolvedValue({ ok: true, value: null, triggered: false, hasData: false, error: null })
    await renderSettled(
      <NotificationWizard groups={GROUPS} rules={[RULE]} onClose={() => {}} onChanged={() => {}} />,
    )
    fireEvent.click(await screen.findByText(ruleSummary(RULE)))
    fireEvent.click(await screen.findByText('Test now'))
    await waitFor(() => expect(screen.getByText(/No data/)).toBeTruthy())
  })
})
