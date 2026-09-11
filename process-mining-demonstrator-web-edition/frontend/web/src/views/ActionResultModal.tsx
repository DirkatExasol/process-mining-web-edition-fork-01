/** Shows the result of running a node-menu action — a log-entry table, a transition
 *  table, or a full process map (flowchart) — inline over the process map. Opened from
 *  the FlowChart node menu. */

import { ActionResultTable } from '../components/ActionResultTable'
import { ActionFlowchart } from '../components/ActionFlowchart'
import { Sheet, Spinner } from '../components/ui'
import type { ActionRunResult } from '../actions/types'

export function ActionResultModal({
  title,
  result,
  busy,
  error,
  onClose,
}: {
  title: string
  result: ActionRunResult | null
  busy: boolean
  error: string | null
  onClose: () => void
}) {
  const isFlowchart = result?.kind === 'flowchart' && result.graph

  return (
    <Sheet title={title} icon="⚡" wide onClose={onClose}>
      {busy && (
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <Spinner />
          <span>Running…</span>
        </div>
      )}
      {error && <p style={{ color: 'var(--red)' }}>{error}</p>}

      {!busy && !error && result && isFlowchart && result.graph && (
        <>
          <p className="fg-secondary" style={{ marginTop: 0, fontSize: 13 }}>
            Process map{result.title ? ` · ${result.title}` : ''}
            {result.journeyCount != null && ` · ${result.journeyCount.toLocaleString()} journeys`}
            {result.dateScoped === false
              ? ' · full range (no data in the current date window)'
              : ' · for the current date range'}
          </p>
          <ActionFlowchart result={result} height="min(70vh, 640px)" />
        </>
      )}

      {!busy && !error && result && !isFlowchart && (
        <>
          <p className="fg-secondary" style={{ marginTop: 0, fontSize: 13 }}>
            {result.kind === 'transitionTable' ? 'Transition table' : 'Log entries'}
            {result.nodeCount != null &&
              ` · ${result.nodeCount} node${result.nodeCount === 1 ? '' : 's'} in scope`}
            {` · ${result.rows.length} row${result.rows.length === 1 ? '' : 's'}`}
          </p>
          <ActionResultTable result={result} />
        </>
      )}
    </Sheet>
  )
}
