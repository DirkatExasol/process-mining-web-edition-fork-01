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
  // The report is a fully self-contained styled HTML document assembled server-side. It is
  // shown on screen in its own iframe (isolated CSS). The frame is same-origin so the host can
  // wire its table-of-contents links, but it is deliberately NOT script-enabled
  // (`sandbox="allow-same-origin allow-modals"`) — the report is static HTML, so even a
  // sanitiser bypass in the embedded content can't run script with our origin.
  const frameRef = useRef<HTMLIFrameElement>(null)

  // "Save as PDF" prints from a THROWAWAY iframe appended to <body>, not the on-screen one.
  // Two reasons the on-screen frame prints blank in Chromium: (1) it is a `srcDoc` frame, and
  // Chromium prints `about:srcdoc` documents empty; (2) it lives inside #root, which the global
  // print stylesheet hides (`@media print { #root { display:none } }`, needed so the Help panel
  // can print a copy portalled to <body>) — a frame under a display:none ancestor has no box to
  // print. The throwaway frame sidesteps both: it is a <body> child (outside the hidden #root)
  // and is filled with document.write, giving a real same-origin about:blank document. No blob:
  // URL (a strict CSP can forbid those) and no `allow-scripts`, so the report stays inert.
  const printReport = () => {
    const html = store.llmAnalysis?.reportHtml
    if (!html) return
    const frame = document.createElement('iframe')
    frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
    frame.setAttribute('aria-hidden', 'true')
    frame.style.cssText = 'position:fixed;left:-9999px;width:0;height:0;border:0;'
    document.body.appendChild(frame)
    const doc = frame.contentWindow?.document
    if (!doc) {
      frame.remove()
      return
    }
    doc.open()
    doc.write(html)
    doc.close()
    let printed = false
    const run = () => {
      if (printed) return
      printed = true
      frame.contentWindow?.focus()
      frame.contentWindow?.print()
      window.setTimeout(() => frame.remove(), 1000)
    }
    // A document.write'd about:blank frame may or may not fire load — cover both, once.
    frame.onload = run
    window.setTimeout(run, 250)
  }

  // Fragment links don't scroll inside a srcDoc frame (base URL is about:srcdoc). The frame
  // is same-origin, so wire the table-of-contents clicks from the host on load. The `href`
  // values are left intact so they still become internal links in the printed PDF.
  const wireTocLinks = () => {
    const doc = frameRef.current?.contentDocument
    if (!doc) return
    doc.querySelectorAll<HTMLAnchorElement>('.toc a[href^="#"]').forEach((link) => {
      link.addEventListener('click', (e) => {
        const target = doc.getElementById(link.getAttribute('href')!.slice(1))
        if (target) {
          e.preventDefault()
          target.scrollIntoView({ block: 'start' })
        }
      })
    })
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
          sandbox="allow-same-origin allow-modals"
          srcDoc={analysis.reportHtml}
          onLoad={wireTocLinks}
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

