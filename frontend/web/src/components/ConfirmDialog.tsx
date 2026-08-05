/** A confirmation dialog styled like the integration wizards / login panels (a narrow
 *  `Sheet`), so the console has one consistent look and feel instead of the browser's
 *  native `window.confirm`. Destructive by default (red confirm button). */

import { Sheet } from './ui'

export function ConfirmDialog({
  title,
  message,
  confirmLabel = 'Delete',
  destructive = true,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string
  message?: string
  confirmLabel?: string
  destructive?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Sheet
      title={title}
      icon={destructive ? '⚠️' : '❓'}
      onClose={onCancel}
      footer={
        <>
          <span className="spacer" />
          <button className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            className={`btn ${destructive ? 'destructive' : 'prominent'}`}
            onClick={onConfirm}
            disabled={busy}
            autoFocus
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <div className="iwiz-col narrow">
        {message && <div className="t-body fg-secondary">{message}</div>}
      </div>
    </Sheet>
  )
}
