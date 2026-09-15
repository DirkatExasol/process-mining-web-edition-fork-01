import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({
  api: {
    sinkIngestInfo: vi.fn(async () => ({
      method: 'POST', path: '/ingest', httpPort: 8129, httpsPort: 8492, tlsMode: 'off',
      activeScheme: 'http', activeContainerPort: 8129,
      consoleHttpPort: 8100, consoleHttpsPort: 8463, titleShort: 'AGENTLOG',
      endpointUrl: '',
    })),
    setSinkEndpoint: vi.fn(async (_id: string, url: string) => ({ endpointUrl: url })),
  },
}))

import { api } from '../api'
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
    // The URL field is pre-filled with the auto-detected URL (no offset in jsdom).
    expect(await screen.findByDisplayValue('http://localhost:8129/ingest')).toBeTruthy()
    // The token field is pre-filled from the just-minted token, and the curl embeds it.
    expect(screen.getByDisplayValue('tok-abc')).toBeTruthy()
    expect(curlText()).toContain('Authorization: Bearer tok-abc')
    expect(screen.getByRole('button', { name: /Download SKILL\.md/ })).toBeTruthy()
  })

  it('uses a placeholder token when opened without one', async () => {
    await renderSettled(<SinkIngestModal sourceId="s1" name="Agent sink" onClose={() => {}} />)
    await screen.findByDisplayValue('http://localhost:8129/ingest')
    expect(curlText()).toContain('Bearer <YOUR_TOKEN>')
  })

  it('pre-fills a saved endpoint-URL override', async () => {
    ;(api.sinkIngestInfo as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      method: 'POST', path: '/ingest', httpPort: 8129, httpsPort: 8492, tlsMode: 'required',
      activeScheme: 'https', activeContainerPort: 8492,
      consoleHttpPort: 8100, consoleHttpsPort: 8463, titleShort: 'AGENTLOG',
      endpointUrl: 'https://pm.example.com/ingest',
    })
    await renderSettled(<SinkIngestModal sourceId="s1" token="tok-abc" onClose={() => {}} />)
    expect(await screen.findByDisplayValue('https://pm.example.com/ingest')).toBeTruthy()
    expect(curlText()).toContain('https://pm.example.com/ingest')
  })

  it('lets the user override the URL and paste a token — both flow into the curl', async () => {
    await renderSettled(<SinkIngestModal sourceId="s1" onClose={() => {}} />)
    const urlInput = await screen.findByDisplayValue('http://localhost:8129/ingest')
    fireEvent.change(urlInput, { target: { value: 'https://pm.example.com/ingest' } })
    fireEvent.change(screen.getByPlaceholderText('<YOUR_TOKEN>'), { target: { value: 'pasted-tok' } })
    await waitFor(() => {
      const c = curlText()
      expect(c).toContain('https://pm.example.com/ingest')
      expect(c).toContain('Authorization: Bearer pasted-tok')
      expect(c).toContain('-k') // https → self-signed flag
    })
  })

  it('persists the URL override via setSinkEndpoint on Save', async () => {
    await renderSettled(<SinkIngestModal sourceId="s1" token="tok-abc" onClose={() => {}} />)
    const urlInput = await screen.findByDisplayValue('http://localhost:8129/ingest')
    fireEvent.change(urlInput, { target: { value: 'https://pm.example.com/ingest' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save$/ }))
    await waitFor(() =>
      expect(api.setSinkEndpoint).toHaveBeenCalledWith('s1', 'https://pm.example.com/ingest'),
    )
  })
})
