import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    sinkIngestInfo: vi.fn(async () => ({
      method: 'POST', path: '/ingest', httpPort: 8129, httpsPort: 8492, tlsMode: 'off',
      activeScheme: 'http', activeContainerPort: 8129,
      consoleHttpPort: 8100, consoleHttpsPort: 8463, titleShort: 'AGENTLOG',
    })),
  },
}))

import { SinkIngestModal } from './SinkIngestModal'
import { renderSettled } from '../test/renderSettled'

afterEach(() => vi.clearAllMocks())

describe('SinkIngestModal', () => {
  const curlText = () =>
    (screen.getAllByRole('textbox') as HTMLTextAreaElement[])
      .map((el) => el.value)
      .find((v) => v.includes('curl')) ?? ''

  it('computes the endpoint URL, embeds the token in curl, and offers SKILL.md', async () => {
    await renderSettled(
      <SinkIngestModal sourceId="s1" token="tok-abc" name="Agent sink" onClose={() => {}} />,
    )
    // The live URL is resolved (http on the sink port, no offset in jsdom).
    expect(await screen.findByDisplayValue('http://localhost:8129/ingest')).toBeTruthy()
    // The curl carries the actual bearer token.
    expect(curlText()).toContain('Authorization: Bearer tok-abc')
    // The downloadable skill is offered.
    expect(screen.getByRole('button', { name: /Download SKILL\.md/ })).toBeTruthy()
  })

  it('uses a placeholder token when opened without one', async () => {
    await renderSettled(<SinkIngestModal sourceId="s1" name="Agent sink" onClose={() => {}} />)
    await screen.findByDisplayValue('http://localhost:8129/ingest')
    expect(curlText()).toContain('Bearer <YOUR_TOKEN>')
  })
})
