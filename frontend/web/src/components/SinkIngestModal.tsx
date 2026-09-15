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

// One journey (all sharing eventId): each event's `step` is a KIND qualified after a
// colon (SKILL:<name>, DATABASE:<db>, WEB:<external|internal>, …); `description` is the
// step's detail (≤256 chars, stored as "Action"); `client`/`user` record who ran it.
const SAMPLE_BODY =
  `[{"eventId":"req-42","step":"SKILL:summarize-sales","description":"Summarize the Q3 sales report and email it to the requester","client":"Claude","user":"alice","eventTime":"2026-09-13T10:00:00"},\n` +
  ` {"eventId":"req-42","step":"DATABASE:sales_db","description":"SELECT region, SUM(amount) FROM sales WHERE quarter='Q3' GROUP BY region","client":"Claude","user":"alice","eventTime":"2026-09-13T10:00:03"},\n` +
  ` {"eventId":"req-42","step":"WEB:external","description":"GET api.exchangerate.host/latest?base=EUR to convert totals","client":"Claude","user":"alice","eventTime":"2026-09-13T10:00:05"},\n` +
  ` {"eventId":"req-42","step":"EMAIL:external","description":"Send the compiled Q3 report to alice@example.com","client":"Claude","user":"alice","eventTime":"2026-09-13T10:00:09"}]`

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
Give every event of the same run the same \`eventId\`. The **first event** names the
originating request; **every later event** names one action you took. Each event's
\`step\` is a **KIND**, qualified after a colon so the map is specific:

- \`SKILL:<skill name>\` — e.g. \`SKILL:summarize-sales\`
- \`TOOL:<type>:<tool name>\` — e.g. \`TOOL:mcp:airfield_get\`
- \`DATABASE:<database name>\` — e.g. \`DATABASE:sales_db\`
- \`WEB:<external|internal>\` — e.g. \`WEB:external\`
- \`EMAIL:<external|internal>\` — e.g. \`EMAIL:external\`
- \`FILE:<local|remote>\` — e.g. \`FILE:local\`
- \`APP:<app name>\` — e.g. \`APP:Slack\`
- \`REQUEST\` — the first event (the originating request); or use the \`SKILL:\`/\`TOOL:\`
  form when the request itself is a skill or tool call.

Keep the KIND from this small set and add the specific target after the colon (the whole
\`KIND:qualifier\` string becomes one node on the map). Put the **detail of the step** —
what exactly it did — in \`description\` (**up to 256 characters**); it is stored as the
event's **Action** attribute. Add \`client\` (which agent — Claude, ChatGPT, …) and
\`user\` (the end user) so the runs can be filtered by who ran what.

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
| \`step\` | yes | A \`KIND:qualifier\` (see above) — becomes a node. Unknown steps are created automatically. |
| \`description\` | recommended | The step's detail, **≤ 256 chars** (e.g. the query run, the URL fetched, the recipient). Stored as the event's **Action** attribute (META_1); longer text is truncated. |
| \`client\` | recommended | The calling client — e.g. \`Claude\`, \`ChatGPT\`. Stored as the **Client** attribute (META_2). |
| \`user\` | optional | The end user, if known. Stored as the **User** attribute (META_3). |
| \`eventTime\` | no | ISO-8601 timestamp; defaults to the server's current time. |

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
- \`step\` is \`KIND:qualifier\` (a node): keep the KIND from the small set, put the target
  after the colon. \`description\` (≤256 chars) is the detail of what the step did.
- Start every journey with the request event, then one event per action you take.
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
  // Editable so the downloaded SKILL.md needs no hand-editing: the endpoint URL (persisted
  // as a per-sink override) and the bearer token (pre-filled when just minted, else pasted
  // — never stored, since only its hash is kept server-side).
  const [urlOverride, setUrlOverride] = useState('')
  const [tokenInput, setTokenInput] = useState(token ?? '')
  const [savingUrl, setSavingUrl] = useState(false)
  const [urlSaved, setUrlSaved] = useState(false)

  useEffect(() => {
    void api
      .sinkIngestInfo(sourceId)
      .then((i) => {
        setInfo(i)
        setUrlOverride(i.endpointUrl || ingestUrl(i)) // saved override, else auto-detected
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [sourceId])

  const autoUrl = info ? ingestUrl(info) : ''
  const url = urlOverride.trim() || autoUrl
  const bearer = tokenInput.trim() || '<YOUR_TOKEN>'
  const insecure = url.startsWith('https') ? ' -k' : '' // self-signed cert
  const curl =
    `curl${insecure} -X POST ${url} \\\n` +
    `  -H "Authorization: Bearer ${bearer}" \\\n` +
    `  -H "Content-Type: application/json" \\\n` +
    `  -d '${SAMPLE_BODY}'`
  const copy = (text: string) => void navigator.clipboard?.writeText(text)
  const sinkName = name || info?.titleShort || 'AI Agent Logging Sink'
  const saveUrl = async () => {
    setSavingUrl(true)
    setError(null)
    try {
      const { endpointUrl } = await api.setSinkEndpoint(sourceId, urlOverride.trim())
      setUrlOverride(endpointUrl || autoUrl)
      setUrlSaved(true)
      setTimeout(() => setUrlSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingUrl(false)
    }
  }
  const downloadSkill = () => {
    if (!info) return
    downloadText('SKILL.md', buildSkillMd({
      name: sinkName, url, curl, tlsMode: info.tlsMode,
      titleShort: info.titleShort, hasToken: Boolean(tokenInput.trim()),
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
              <span className="t-caption fg-secondary">Endpoint URL (editable — saved for this sink)</span>
              <div className="row" style={{ gap: 6 }}>
                <input
                  className="text-input"
                  value={urlOverride}
                  onChange={(e) => setUrlOverride(e.target.value)}
                  placeholder={autoUrl}
                  spellCheck={false}
                  style={{ fontFamily: 'var(--mono, monospace)' }}
                />
                <button className="btn small" onClick={() => void saveUrl()} disabled={savingUrl}>
                  {savingUrl ? 'Saving…' : urlSaved ? '✓ Saved' : 'Save'}
                </button>
                <button className="btn small" onClick={() => copy(url)}>Copy</button>
              </div>
              <span className="t-caption2 fg-tertiary">
                Override with a public URL (e.g. a reverse-proxy domain) so the SKILL.md is
                ready to use.{' '}
                {urlOverride.trim() && urlOverride.trim() !== autoUrl && (
                  <button
                    className="btn-link"
                    onClick={() => setUrlOverride(autoUrl)}
                    style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', color: 'var(--accent)' }}
                  >
                    reset to auto-detected
                  </button>
                )}
              </span>
            </label>

            <label className="col" style={{ gap: 4 }}>
              <span className="t-caption fg-secondary">
                Bearer token {token ? '(from creation — shown once)' : '(paste it to embed in the SKILL.md)'}
              </span>
              <input
                className="text-input"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="<YOUR_TOKEN>"
                spellCheck={false}
                autoComplete="off"
                style={{ fontFamily: 'var(--mono, monospace)' }}
              />
            </label>

            <label className="col" style={{ gap: 4 }}>
              <span className="t-caption fg-secondary">
                Ready-to-run curl {tokenInput.trim() ? '(with your token)' : '(paste your token above)'}
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
                The token is shown once, when the sink is created or regenerated — the server
                keeps only its hash, so it can't be shown here again. Paste it above to embed
                it in the download, or use the 🔑 button on the sink to mint a fresh one.
              </div>
            )}

            <div className="t-caption2 fg-tertiary">
              Each entry needs <code>eventId</code> (the journey) and <code>step</code> (the
              request/action KIND); add <code>description</code> (→ Action),{' '}
              <code>client</code> (→ Client) and <code>user</code> (→ User).{' '}
              <code>eventTime</code> defaults to now. See the SKILL.md for how to model a
              journey. TLS mode: <strong>{info.tlsMode}</strong>{' '}
              (container port {info.activeContainerPort}).
            </div>
          </>
        )}
      </div>
    </Sheet>
  )
}
