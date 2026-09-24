/** AI documentation view — renders the server-assembled report HTML in an isolated on-screen
 *  iframe, and "Save as PDF" prints from a throwaway <body> iframe written via document.write
 *  (a srcDoc frame, or a frame under the print-hidden #root, prints blank in Chromium). */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AIDocumentationView } from './AIDocumentationView'
import { useStore } from '../store'

const REPORT_HTML =
  '<!doctype html><html><body><h1>My Process</h1><p>The process is healthy and efficient.</p></body></html>'

function seedReport() {
  useStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    selectedProject: { projectId: 'p', title: 'My Process' } as any,
    isLLMAnalyzing: false,
    llmAnalysisError: null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    connection: { isLLMReachable: true } as any,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    llmAnalysis: {
      reportHtml: REPORT_HTML,
      findings: null,
      prompt: 'analyse this',
      model: 'gpt-4o',
    } as any,
  })
}

describe('AIDocumentationView', () => {
  it('renders the report on screen and prints from a throwaway body iframe', () => {
    vi.useFakeTimers()
    seedReport()
    const { container } = render(<AIDocumentationView />)

    // On-screen: an isolated, script-disabled srcDoc frame (unchanged display path).
    const onscreen = container.querySelector('iframe.ai-report-frame') as HTMLIFrameElement
    expect(onscreen).not.toBeNull()
    expect(onscreen.getAttribute('srcdoc')).toContain('healthy and efficient')
    expect(onscreen.getAttribute('sandbox')).toBe('allow-same-origin allow-modals')

    // "Save as PDF" must NOT print the on-screen srcDoc frame (blank in Chromium). It creates
    // a fresh iframe, writes the report into it, and prints THAT.
    const printSpy = vi.fn()
    const writeSpy = vi.fn()
    let printFrame: HTMLElement | null = null
    const realCreate = document.createElement.bind(document)
    const createSpy = vi
      .spyOn(document, 'createElement')
      .mockImplementation(((tag: string) => {
        const el = realCreate(tag)
        if (tag === 'iframe') {
          printFrame = el
          Object.defineProperty(el, 'contentWindow', {
            configurable: true,
            value: {
              focus: vi.fn(),
              print: printSpy,
              close: vi.fn(), // jsdom teardown calls window.close() on child frames
              document: { open: vi.fn(), write: writeSpy, close: vi.fn() },
            },
          })
        }
        return el
      }) as typeof document.createElement)

    fireEvent.click(screen.getByRole('button', { name: /Save as PDF/ }))
    vi.advanceTimersByTime(300) // fires the print fallback (250ms), not the removal (1000ms)

    expect(printFrame).not.toBeNull()
    // Appended to <body> (outside the print-hidden #root) and script-disabled.
    expect(printFrame!.parentElement).toBe(document.body)
    expect(printFrame!.getAttribute('sandbox')).toBe('allow-same-origin allow-modals')
    // Written via document.write (a real about:blank doc, not srcDoc), then printed.
    expect(writeSpy).toHaveBeenCalledWith(REPORT_HTML)
    expect(printSpy).toHaveBeenCalled()

    printFrame!.remove()
    createSpy.mockRestore()
    vi.useRealTimers()
  })

  it('shows the failure state when the analysis errored (no report)', () => {
    useStore.setState({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      selectedProject: { projectId: 'p', title: 'My Process' } as any,
      isLLMAnalyzing: false,
      llmAnalysis: null,
      llmAnalysisError: 'LLM unreachable',
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      connection: { isLLMReachable: true } as any,
    })
    render(<AIDocumentationView />)
    expect(screen.getByText('Analysis Failed')).toBeInTheDocument()
    expect(screen.getByText('LLM unreachable')).toBeInTheDocument()
  })
})
