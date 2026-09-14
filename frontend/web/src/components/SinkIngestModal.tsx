/** A popup showing a sink's exact ingest request — the full URL and a ready-to-copy
 *  curl (correct scheme/port for the current TLS mode, hostname, token, JSON body) so
 *  the user never has to construct the endpoint by hand. Opened from the "Sink created"
 *  panel, the regenerate-token dialog, and each sink badge. */

import { useEffect, useState } from 'react'
import { api } from '../api'
import { Sheet } from './ui'

type Info = Awaited<ReturnType<typeof api.sinkIngestInfo>>

/** Resolve the host-visible URL: the sink's live scheme + its container port mapped to
 *  the host by the SAME offset the console itself is reached under (Docker publishes +10000;
 *  a bare run uses +0). Detected from the console's own external vs container port. */
function ingestUrl(info: Info): string {
  const loc = window.location
  const isHttps = loc.protocol === 'https:'
  const consoleContainer = isHttps ? info.consoleHttpsPort : info.consoleHttpPort
  const shown = Number(loc.port) || (isHttps ? 443 : 80)
  let offset = shown - consoleContainer
  if (!Number.isFinite(offset) || offset < 0) offset = 0 // dev server / unknown → no offset
  const hostPort = info.activeContainerPort + offset
  return `${info.activeScheme}://${loc.hostname}:${hostPort}${info.path}`
}

// One journey (all sharing eventId): the FIRST event names the TYPE of request; each
// later event names the KIND of action taken. `description` (≤50 chars) says the specifics.
const SAMPLE_BODY =
  `[{"eventId":"req-42","step":"SKILL","description":"Summarize quarterly sales","eventTime":"2026-09-13T10:00:00"},\n` +
  ` {"eventId":"req-42","step":"DATABASE","description":"Query sales table","eventTime":"2026-09-13T10:00:03"},\n` +
  ` {"eventId":"req-42","step":"WEB","description":"Fetch exchange rates","eventTime":"2026-09-13T10:00:05"},\n` +
  ` {"eventId":"req-42","step":"EMAIL","description":"Send report to requester","eventTime":"2026-09-13T10:00:09"}]`

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

/** A self-contained skill document an AI agent can be handed to POST its journey events
 *  to this sink — every concrete detail (URL, token, auth, schema, examples) filled in. */
function buildSkillMd(o: {
  name: string
  url: string
  curl: string
  tlsMode: string
  titleShort: string
  hasToken: boolean
}): string {
  return `# Skill: Emit process-mining journey events to "${o.name}"

## When to use
Use this skill to record what an agent does as **journey events**, so the runs appear as a
live process map in the Process Mining Demonstrator. One **journey** = one request/run you
handle; one **event** = one step within it. Emit an event as each step happens and reuse the
same \`eventId\` for every event of that journey so they link into a single path.

## How to model a journey
Give every event of the same run the same \`eventId\`. Then choose each event's \`step\`
and \`description\`:

- **First event of the journey** — \`step\` is the **type of request** you received:
  \`SKILL\`, \`REQUEST\`, \`TOOL USE\`, \`CHAT\`, … . Put what it is in \`description\`
  (≤ 50 chars), e.g. \`"Summarize quarterly sales"\`.
- **Every later event** — \`step\` is the **kind of action** you took: \`REQUEST\`,
  \`SKILL\`, \`TOOL\`, \`DATABASE\`, \`WEB\`, \`EMAIL\`, \`FILE\`, \`APP\`, … . Put the
  specifics in \`description\` (≤ 50 chars), e.g. \`"Query sales table"\`,
  \`"Fetch exchange rates"\`, \`"Send report to requester"\`.

Keep \`step\` to a small, stable vocabulary of KINDS (they become the nodes on the map);
let \`description\` carry the detail (it is written onto the STEP as its description).

## Endpoint
- **Method / URL:** \`POST ${o.url}\`
- **Auth:** \`Authorization: Bearer <TOKEN>\` (required)${
    o.hasToken ? ' — your token is embedded in the example below.' : ' — paste the token you were given.'
  }
- **Content-Type:** \`application/json\`
- **TLS mode:** ${o.tlsMode}${o.url.startsWith('https') ? ' — the certificate is self-signed; disable verification (curl `-k`) or trust it.' : ' — plain HTTP.'}
- **Target project:** every event lands in project \`${o.titleShort}\` (created if new).

## Request body
A single JSON object, or an array of them. Each object:

| field | required | notes |
|-------|----------|-------|
| \`eventId\` | yes | The journey / request id. Reuse it across all events of one run. |
| \`step\` | yes | The KIND of request/action (see above) — becomes a node. Unknown kinds are created automatically. |
| \`description\` | recommended | Free text, ≤ 50 chars, describing the request/action. Written onto the STEP record (its description), set from the first event that introduces the step. |
| \`eventTime\` | no | ISO-8601 timestamp; defaults to the server's current time. |
| \`meta1\`, \`meta2\`, \`meta3\` | no | Optional extra free-text attributes carried on the event. |

## Example
\`\`\`bash
${o.curl}
\`\`\`

## Responses
- \`200\` — \`{"ingested": N, "newSteps": [...], "projectId": <n>}\`
- \`400\` — malformed JSON, or an entry missing \`eventId\`/\`step\`
- \`401\` — missing or invalid bearer token
- \`503\` — the sink module is disabled in the admin interface

## Rules of thumb
- Send events in the order they happen; \`eventTime\` (or arrival order) determines the path.
- \`step\` is a KIND (a node); keep the set small and stable. \`description\` is the detail.
- Start every journey with the request-type event, then one event per action you take.
- Batch multiple events in one array to reduce round-trips.
- Treat the token as a secret; if it leaks, regenerate it (the old one stops working).
`
}

export function SinkIngestModal({
  sourceId,
  token,
  name,
  onClose,
}: {
  sourceId: string
  token?: string
  name?: string
  onClose: () => void
}) {
  const [info, setInfo] = useState<Info | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api
      .sinkIngestInfo(sourceId)
      .then(setInfo)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [sourceId])

  const url = info ? ingestUrl(info) : ''
  const bearer = token ?? '<YOUR_TOKEN>'
  const insecure = info?.activeScheme === 'https' ? ' -k' : '' // self-signed cert
  const curl =
    `curl${insecure} -X POST ${url} \\\n` +
    `  -H "Authorization: Bearer ${bearer}" \\\n` +
    `  -H "Content-Type: application/json" \\\n` +
    `  -d '${SAMPLE_BODY}'`
  const copy = (text: string) => void navigator.clipboard?.writeText(text)
  const sinkName = name || info?.titleShort || 'AI Agent Logging Sink'
  const downloadSkill = () => {
    if (!info) return
    downloadText('SKILL.md', buildSkillMd({
      name: sinkName, url, curl, tlsMode: info.tlsMode,
      titleShort: info.titleShort, hasToken: Boolean(token),
    }))
  }

  return (
    <Sheet
      title="Ingest endpoint"
      icon="🔌"
      onClose={onClose}
      footer={
        <>
          <span className="spacer" />
          <button className="btn prominent" onClick={onClose}>Done</button>
        </>
      }
    >
      <div className="col" style={{ gap: 10 }}>
        {error && <div className="t-caption fg-red">{error}</div>}
        {!info ? (
          <div className="fg-tertiary">Loading…</div>
        ) : (
          <>
            <div className="t-caption2 fg-tertiary">
              POST journey entries here. Entries land in project <strong>{info.titleShort}</strong>;
              unknown steps are created. {info.activeScheme === 'https'
                ? 'TLS is on — the cert is self-signed, so use curl’s -k (or trust it).'
                : 'TLS is off for this surface — this is a plain-HTTP endpoint.'}
            </div>

            <label className="col" style={{ gap: 4 }}>
              <span className="t-caption fg-secondary">Endpoint URL</span>
              <div className="row" style={{ gap: 6 }}>
                <input
                  className="text-input"
                  readOnly
                  value={url}
                  onFocus={(e) => e.currentTarget.select()}
                  style={{ fontFamily: 'var(--mono, monospace)' }}
                />
                <button className="btn small" onClick={() => copy(url)}>Copy</button>
              </div>
            </label>

            <label className="col" style={{ gap: 4 }}>
              <span className="t-caption fg-secondary">
                Ready-to-run curl {token ? '(with your token)' : '(paste your token)'}
              </span>
              <textarea
                className="text-input"
                readOnly
                value={curl}
                onFocus={(e) => e.currentTarget.select()}
                rows={6}
                style={{ fontFamily: 'var(--mono, monospace)', fontSize: 12, whiteSpace: 'pre' }}
              />
              <div className="row" style={{ gap: 8 }}>
                <button className="btn small" onClick={() => copy(curl)}>Copy curl</button>
                <button className="btn small" onClick={downloadSkill}>⬇ Download SKILL.md</button>
              </div>
            </label>

            {!token && (
              <div className="t-caption2 fg-tertiary">
                The token is shown only when the sink is created or regenerated — use the 🔑
                button on the sink to mint a fresh one.
              </div>
            )}

            <div className="t-caption2 fg-tertiary">
              Each entry needs <code>eventId</code> (the journey) and <code>step</code> (the
              request/action KIND); add a <code>description</code> (≤50 chars, becomes the
              step's description). <code>eventTime</code> defaults to now. See the SKILL.md
              for how to model a journey. TLS mode: <strong>{info.tlsMode}</strong>{' '}
              (container port {info.activeContainerPort}).
            </div>
          </>
        )}
      </div>
    </Sheet>
  )
}
