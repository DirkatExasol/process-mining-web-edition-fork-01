/** AI documentation print — the report must be portalled to <body> so it prints
 *  (the global print stylesheet hides #root). Guards against the "one empty
 *  page" regression where the button called window.print() directly. */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { AIDocumentationView } from './AIDocumentationView'
import { useStore } from '../store'

function seedAnalysisResult() {
  useStore.setState({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    selectedProject: { projectId: 'p', title: 'My Process' } as any,
    isLLMAnalyzing: false,
    llmAnalysisError: null,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    connection: { isLLMReachable: true } as any,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    llmAnalysis: {
      result: 'The process is healthy and efficient.',
      prompt: 'analyse this',
      model: 'gpt-4o',
    } as any,
  })
}

describe('AIDocumentationView print', () => {
  it('portals a print-only copy of the report to <body> when printing', () => {
    // Run the rAF callback synchronously and stub the print dialog.
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 0
    })
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {})

    seedAnalysisResult()
    render(<AIDocumentationView />)

    // Nothing portalled until the button is pressed.
    expect(document.body.querySelector('.ai-print-doc')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Print \/ PDF/ }))

    expect(printSpy).toHaveBeenCalled()
    const printDoc = document.body.querySelector('.ai-print-doc')
    expect(printDoc).not.toBeNull()
    // It contains the report — the project title and the analysis text.
    expect(printDoc?.textContent).toContain('My Process')
    expect(printDoc?.textContent).toContain('healthy and efficient')
  })
})
