/** Shows the result of running a node-menu action — a log-entry table or a transition
 *  table — inline over the process map. Opened from the FlowChart node menu. */

import { ActionResultTable } from '../components/ActionResultTable'
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
  return (
    <Sheet title={title} icon="⚡" wide onClose={onClose}>
      {busy && (
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <Spinner />
          <span>Running…</span>
        </div>
      )}
      {error && <p style={{ color: 'var(--red)' }}>{error}</p>}
      {!busy && !error && result && (
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
