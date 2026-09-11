/** First-run legal disclaimer — ports `LegalDisclaimerView` from ContentView.swift.
 *  (The launch splash was removed — it re-appeared on every browser refresh.) */

import { useState } from 'react'
import { Divider } from './ui'

const SECTIONS = [
  {
    heading: 'Purpose and scope',
    body: 'This application is provided for educational and exploratory purposes only. Any productive or business-critical use is the sole responsibility of the user.',
  },
  {
    heading: 'AI-generated results',
    body: 'Process Mining Demonstrator includes AI-powered analysis features that use large language models to interpret process data. AI models can produce results that are incorrect, incomplete, or misleading.',
  },
  {
    heading: 'Data accuracy',
    body: 'Process maps, KPIs, journey statistics, and all other computed results depend entirely on the quality, completeness, and correctness of the data stored in your database.',
  },
]

export function LegalGate({
  onAccept,
  onDecline,
}: {
  onAccept: () => void
  onDecline: () => void
}) {
  const [accepted, setAccepted] = useState(false)

  return (
    <div className="scrim">
      <div className="legal-gate" role="dialog" aria-modal="true">
        <div className="col" style={{ alignItems: 'center', gap: 6, padding: '32px 24px 20px' }}>
          <span style={{ fontSize: 38 }} aria-hidden>
            ⛔️
          </span>
          <span className="t-title3">Legal Disclaimer</span>
          <span className="t-subheadline fg-secondary">
            Please read carefully before continuing
          </span>
        </div>
        <Divider />

        <div className="scroll-view" style={{ gap: 18 }}>
          {SECTIONS.map((section) => (
            <div key={section.heading} className="col" style={{ gap: 6 }}>
              <span className="t-subheadline" style={{ fontWeight: 600 }}>
                {section.heading}
              </span>
              <span
                className="t-subheadline fg-secondary"
                style={{ whiteSpace: 'pre-wrap' }}
              >
                {section.body}
              </span>
            </div>
          ))}

          <div className="legal-note col" style={{ gap: 8 }}>
            <span
              className="t-subheadline fg-orange"
              style={{ fontWeight: 600 }}
            >
              🖥 Device transfer
            </span>
            <span className="t-subheadline">
              Acceptance of this disclaimer is recorded for this installation. If this
              device or account is handed to another person, the obligation to comply
              with these terms and the acknowledgement of their content passes
              automatically to the new user, who is bound by them from the moment they
              first operate the application.
            </span>
          </div>
        </div>

        <Divider />
        <div className="col" style={{ padding: 20, gap: 14 }}>
          <label className="row t-subheadline" style={{ gap: 10 }}>
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
            />
            I have read and accept all terms stated above
          </label>
          <div className="row" style={{ gap: 10 }}>
            <button
              className="btn"
              style={{ padding: '12px', fontSize: 15, flex: 1 }}
              onClick={onDecline}
            >
              Decline
            </button>
            <button
              className="btn prominent"
              style={{ padding: '12px', fontSize: 15, flex: 1 }}
              disabled={!accepted}
              onClick={onAccept}
            >
              Accept &amp; Continue
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
