/** AI documentation view — renders the server-assembled report HTML in an isolated iframe
 *  and prints that frame (the same Chrome-print path that produced the reference report). */
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
  it('renders the assembled report in an iframe and prints that frame', () => {
    seedReport()
    const { container } = render(<AIDocumentationView />)

    const frame = container.querySelector('iframe.ai-report-frame') as HTMLIFrameElement
    expect(frame).not.toBeNull()
    expect(frame.getAttribute('srcdoc')).toContain('healthy and efficient')
    // The frame is same-origin (so the host can print it and wire its links) but is NOT
    // script-enabled — the report is static, so a sanitiser bypass can't run with our origin.
    expect(frame.getAttribute('sandbox')).toBe('allow-same-origin allow-modals')

    // "Save as PDF" prints the on-screen report frame directly (no blob: — a strict CSP can
    // forbid blob: documents).
    const printSpy = vi.fn()
    Object.defineProperty(frame, 'contentWindow', {
      configurable: true,
      value: { focus: vi.fn(), print: printSpy },
    })
    fireEvent.click(screen.getByRole('button', { name: /Save as PDF/ }))
    expect(printSpy).toHaveBeenCalled()
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
