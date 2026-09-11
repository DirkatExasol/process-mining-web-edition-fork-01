/** Renders an action's result — a generic {columns, rows} table — shared by the
 *  Actions builder's Test panel and the app's node-menu result modal. */

import type { ActionRunResult } from '../actions/types'

export function ActionResultTable({ result }: { result: ActionRunResult }) {
  if (!result.columns.length || !result.rows.length) {
    return (
      <p className="fg-secondary" style={{ margin: '8px 0' }}>
        No rows matched — try a wider node scope or relax the chart filters.
      </p>
    )
  }
  return (
    <div style={{ overflowX: 'auto', maxHeight: '50vh', overflowY: 'auto' }}>
      <table className="data-table" style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
        <thead>
          <tr>
            {result.columns.map((c) => (
              <th
                key={c}
                style={{
                  textAlign: 'left',
                  padding: '6px 10px',
                  borderBottom: '1px solid var(--border)',
                  position: 'sticky',
                  top: 0,
                  background: 'var(--bg-secondary-grouped, var(--bg-secondary))',
                  whiteSpace: 'nowrap',
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td
                  key={j}
                  style={{
                    padding: '5px 10px',
                    borderBottom: '1px solid var(--border)',
                    whiteSpace: 'nowrap',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {cell === null || cell === undefined ? '—' : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
