/** AI supported Documentation — port of `aiAnalysisContent` from ProcessMapView.
 *
 * Before a run: shows the A-Chart filter context plus notices about happy paths
 * and norms. After: renders the assembled report (analysis, journey paths, happy
 * path conformance, conformance gaps, user comments, analysis parameters). */

import { useState } from 'react'
import { Markdown } from '../components/Markdown'
import { Sheet, Unavailable } from '../components/ui'
import { formatDateTime } from '../graph/format'
import { aChartFilterSummary, useStore } from '../store'
import { noteTargetLabel } from '../types'

export function AIDocumentationView() {
  const store = useStore()
  const [showPrompt, setShowPrompt] = useState(false)

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
  if (analysis?.result) {
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
          <button className="btn small" onClick={() => window.print()}>
            ⎙ Print / PDF
          </button>
          <button
            className="btn small"
            disabled={!llmReachable}
            onClick={() => void store.runLLMAnalysis()}
          >
            ↻ Re-run
          </button>
        </div>

        <div className="scroll-view">
          <Markdown text={buildReport(store, analysis)} />
        </div>

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
            disabled={!llmReachable}
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
        disabled={!llmReachable}
        onClick={() => void store.runLLMAnalysis()}
      >
        🧠 AI supported Documentation
      </button>

      {!llmReachable && (
        <span
          className="t-caption fg-orange"
          style={{ maxWidth: 320, textAlign: 'center' }}
        >
          ⚠ LLM server not reachable. Check your connection profile.
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

/** Assembles the report the way `reportDocument` does in the Swift view. */
function buildReport(
  store: ReturnType<typeof useStore.getState>,
  analysis: NonNullable<ReturnType<typeof useStore.getState>['llmAnalysis']>,
): string {
  const project = store.selectedProject
  const parts: string[] = []

  parts.push(`# ${project?.title ?? 'Process Documentation'}`)
  parts.push('_AI-Supported Process Documentation_')
  parts.push(`> ${aChartFilterSummary(store)}`)
  if (analysis.generatedAt) {
    parts.push(`> Generated: ${formatDateTime(analysis.generatedAt)}`)
  }
  parts.push('---')
  parts.push('## 1. AI Analysis')
  parts.push(analysis.result?.trim() ?? '')

  let chapter = 2
  if (analysis.journeyPathsSummary) {
    parts.push(
      analysis.journeyPathsSummary.replace(
        /^\s*## Journey Paths/m,
        `## ${chapter++}. Journey Paths`,
      ),
    )
  }
  if (analysis.happyPathSummary) {
    parts.push(
      analysis.happyPathSummary.replace(
        /^\s*## Happy Path Conformance/m,
        `## ${chapter++}. Happy Path Conformance`,
      ),
    )
  }
  if (analysis.conformanceSummary) {
    parts.push(
      analysis.conformanceSummary.replace(
        /^\s*## Conformance Check – Gap Analysis/m,
        `## ${chapter++}. Conformance Check – Gap Analysis`,
      ),
    )
  }

  if (store.projectNotes.length > 0) {
    const sorted = [...store.projectNotes].sort((a, b) =>
      a.createdAt.localeCompare(b.createdAt),
    )
    let table = `## ${chapter++}. User Comments\n\n`
    table += '| Element | Type | User | Note | Date |\n'
    table += '|---------|------|------|------|------|\n'
    for (const note of sorted) {
      const text = note.text.replace(/\|/g, '｜').replace(/\n/g, '<br>')
      table += `| ${noteTargetLabel(note.target)} | ${
        note.target.type === 'edge' ? 'Edge' : 'Node'
      } | ${note.authorName || note.username || '—'} | ${text} | ${formatDateTime(note.createdAt)} |\n`
    }
    parts.push(table)
  }

  let params = `## ${chapter}. Analysis Parameters\n\n`
  if (analysis.model) params += `**Model:** \`${analysis.model}\`\n\n`
  if (store.llmPromptTemplate) {
    params += '**Prompt template:**\n\n'
    params += store.llmPromptTemplate
      .split('\n')
      .map((line) => `> ${line}`)
      .join('\n')
  }
  parts.push(params)

  return parts.join('\n\n')
}
