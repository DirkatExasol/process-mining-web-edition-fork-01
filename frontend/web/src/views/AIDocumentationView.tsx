/** AI supported Documentation — port of `aiAnalysisContent` from ProcessMapView.
 *
 * Before a run: shows the A-Chart filter context plus notices about happy paths
 * and norms. After: renders the assembled report (analysis, journey paths, happy
 * path conformance, conformance gaps, user comments, analysis parameters). */

import { useRef, useState } from 'react'
import { Sheet, Unavailable } from '../components/ui'
import { aChartFilterSummary, useStore } from '../store'

export function AIDocumentationView() {
  const store = useStore()
  const [showPrompt, setShowPrompt] = useState(false)
  // The report is a fully self-contained styled HTML document assembled server-side. It
  // renders in its own iframe (its CSS is isolated from the app), and "Save as PDF" prints
  // that frame — the same Chrome-print path that produced the reference report.
  const frameRef = useRef<HTMLIFrameElement>(null)
  // The report is shown in its own iframe (isolated CSS). The frame is same-origin so the
  // host can trigger printing on it; it also runs the report's embedded script (which owns
  // the table-of-contents scrolling — fragment links don't resolve against about:srcdoc) and
  // may open the print dialog (allow-modals). We print THIS frame directly (rather than a
  // blob: URL) because a strict Content-Security-Policy can forbid blob: documents.
  const printReport = () => {
    const win = frameRef.current?.contentWindow
    if (!win) return
    win.focus()
    win.print()
  }

  const summary = aChartFilterSummary(store)
  const llmReachable = store.connection.isLLMReachable

  if (!store.selectedProject) {
    return (
      <Unavailable
        glyph="🗺"
        title="No Project Selected"
        description="Select a project from the sidebar."
      />
    )
  }

  if (store.isLLMAnalyzing) {
    return (
      <div className="center-fill">
        <span className="spinner large" />
        <span>AI is analyzing</span>
        <span className="t-caption fg-tertiary" style={{ maxWidth: 420, textAlign: 'center' }}>
          {summary}
        </span>
      </div>
    )
  }

  const analysis = store.llmAnalysis
  if (analysis?.reportHtml) {
    return (
      <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
        <div
          className="row"
          style={{
            padding: '8px 16px',
            gap: 8,
            background: 'var(--bg-tertiary-grouped)',
            borderBottom: '1px solid var(--separator-soft)',
          }}
        >
          <span aria-hidden className="fg-secondary">
            ⛃
          </span>
          <span className="t-caption fg-secondary truncate spacer">{summary}</span>
          <button className="btn small" onClick={() => setShowPrompt(true)}>
            Show prompt
          </button>
          <button className="btn small prominent" onClick={printReport}>
            ⎙ Save as PDF
          </button>
          <button
            className="btn small"
            onClick={() => void store.runLLMAnalysis()}
          >
            ↻ Re-run
          </button>
        </div>

        <iframe
          ref={frameRef}
          title="AI report"
          className="ai-report-frame"
          sandbox="allow-same-origin allow-scripts allow-modals"
          srcDoc={analysis.reportHtml}
        />

        {showPrompt && (
          <Sheet title="Prompt sent to the LLM" wide onClose={() => setShowPrompt(false)}>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{analysis.prompt}</pre>
          </Sheet>
        )}
      </div>
    )
  }

  if (store.llmAnalysisError) {
    return (
      <Unavailable
        glyph="⚠️"
        title="Analysis Failed"
        description={store.llmAnalysisError}
        action={
          <button
            className="btn prominent"
            onClick={() => void store.runLLMAnalysis()}
          >
            ↻ Try Again
          </button>
        }
      />
    )
  }

  const normCount = Object.values(store.targetNorms).reduce(
    (sum, metricNorms) => sum + Object.keys(metricNorms).length,
    0,
  )
  const metricCount = Object.values(store.targetNorms).filter(
    (m) => Object.keys(m).length > 0,
  ).length

  return (
    <div
      className="col"
      style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, padding: 24 }}
    >
      <span style={{ fontSize: 56, opacity: 0.35 }} aria-hidden>
        🧠
      </span>

      <NoticeCard title="A-Chart filters in use" icon="⛃">
        {summary}
      </NoticeCard>

      <NoticeCard
        title="Happy Path Conformance"
        icon="🪧"
        warning={store.happyPaths.length === 0}
      >
        {store.happyPaths.length === 0
          ? 'No Happy Paths defined — conformance data will not be included. Create one in the Happy Path view to enrich the analysis.'
          : `${store.happyPaths.length} path${
              store.happyPaths.length === 1 ? '' : 's'
            } will be evaluated: ${store.happyPaths.map((p) => p.name).join(', ')}`}
      </NoticeCard>

      <NoticeCard title="Conformance Check" icon="🛡️" warning={normCount === 0}>
        {normCount === 0
          ? 'No norms defined — gap analysis will not be included. Open Conformance Check and click edges in Edit mode to define target values.'
          : `${normCount} norm${normCount === 1 ? '' : 's'} across ${metricCount} metric${
              metricCount === 1 ? '' : 's'
            } — gap analysis will be appended to the report.`}
      </NoticeCard>

      <button
        className="btn prominent"
        style={{ minWidth: 220, padding: '9px 16px' }}
        onClick={() => void store.runLLMAnalysis()}
      >
        🧠 AI supported Documentation
      </button>

      {!llmReachable && (
        <span
          className="t-caption fg-secondary"
          style={{ maxWidth: 360, textAlign: 'center' }}
        >
          The report uses the LLM configured in the admin Reporting tab if set, otherwise
          your connection's LLM (which currently looks unreachable).
        </span>
      )}
    </div>
  )
}

function NoticeCard({
  title,
  icon,
  warning = false,
  children,
}: {
  title: string
  icon: string
  warning?: boolean
  children: React.ReactNode
}) {
  return (
    <div
      className="col"
      style={{
        gap: 6,
        padding: 14,
        maxWidth: 380,
        width: '100%',
        borderRadius: 10,
        background: 'var(--bg-secondary-grouped)',
        border: `1px solid ${warning ? 'rgba(255,149,0,0.45)' : 'var(--separator-soft)'}`,
      }}
    >
      <span
        className="t-caption"
        style={{ fontWeight: 600, color: warning ? 'var(--orange)' : 'var(--secondary)' }}
      >
        {icon} {title}
      </span>
      <span className="t-caption fg-secondary">{children}</span>
    </div>
  )
}

