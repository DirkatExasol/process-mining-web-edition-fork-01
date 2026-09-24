# MCP Server — setup guide

The **MCP server** is a [Model Context Protocol](https://modelcontextprotocol.io) endpoint
that lets AI clients (Claude, ChatGPT, …) query your Process Mining data — **metrics, paths,
cases, metadata and notes** — over HTTP(S). Callers authenticate with an **OAuth access
token issued by your Authentik server**; the token is verified against Authentik's signing
keys and mapped to a Process Mining user, whose assigned database connections decide what
they may see. It is **read-only except for notes**: `create_note` and `update_note` are the
only write tools (no ingest, event-editing or sampling tools exist), and the five
deeper-analysis tools are reserved for **power users**.

It is the seventh surface, on the admin port **+40**: **HTTP 8130 / HTTPS 8493** in the
container, published by Docker at **18130 / 18493** on the host. It is **off until an
administrator enables it** (admin panel → *MCP Server* tab) and returns `503` while off.

```
AI client ──OAuth──▶ Authentik (:19443)          the client gets an access token
AI client ──MCP/JSON-RPC + Bearer token──▶ MCP server (:18493/mcp)
                          └─ verifies the token against Authentik's JWKS
                          └─ maps it to a Process Mining user
                          └─ answers queries on that user's connections (writes: notes only)
```

---

## What the server exposes (MCP tools)

Nineteen tools in five groups. Who may call them:

- **Everyone** with an MCP login: the discovery, analysis, case and note-reading tools.
- **Writes — notes only.** `create_note` and `update_note` follow the app's own note rules:
  the author is always the signed-in user; ids and times are set by the server; a thread is
  append-only (comments are prepended, nothing is rewritten); only a note's author may change
  its severity or scope; another user's private note is indistinguishable from a missing one.
  Every field is validated (step names must exist in the project, text ≤ 4000 and title ≤ 200
  characters, control and bidi-override characters stripped, and no text can imitate a
  thread entry's header to pose as another author), a full thread (100,000 characters) takes
  no more comments, the permission rule is re-checked inside the database write itself, each
  user may make at most
  `PMW_MCP_NOTE_WRITES_PER_MIN` (default 20) note changes per minute, and every write is
  recorded in the admin log (who, which note — never the text).
- **Power users & administrators** — `compare_segments`, `get_bottlenecks`, `get_trend`,
  `get_outcome_drivers`, `check_conformance`. Grant the role in the admin console (**Users** tab →
  **Make power**). Anyone else receives a polite refusal that names the role and suggests the
  everyday tools instead; nothing is queried.

**Times.** Note timestamps are local time in the **display timezone set in the Admin
Console** (App Control → *Timezone*) and are returned with that zone's UTC offset, e.g.
`2026-09-23T12:34:45+02:00`. Journey event times are the event log's own recorded times.

<!-- MCP-TOOL-REFERENCE:BEGIN -->
### Tool reference — 19 tools, one example each

| Tool | Who | Returns |
|---|---|---|
| `list_connections` | Everyone | The database connections you may query. |
| `list_projects` | Everyone | Projects on one connection — or, with connectionId omitted, on every connection you may query; includeCounts adds a journey count per project. |
| `get_metadata` | Everyone | Meta-attribute titles, step names, each step's definition (stepDetails: description, score, belongsTo group, endOfProcess, shape) and the event date range. |
| `get_attribute_values` | Everyone | The values each meta attribute takes, with journey counts, most frequent first — so you know what to pass as meta1/meta2/meta3. |
| `get_process_map` | Everyone | The directly-follows map: steps (nodes) and transitions (edges) with counts and timing. |
| `get_transition_metrics` | Everyone | Per step pair: count and average/median/min/max/stddev transition time (seconds). |
| `get_variants` | Everyone | Distinct journey paths and how often each occurs, most frequent first. |
| `get_statistics` | Everyone | Journey count, journey-duration statistics and the process-goodness score. |
| `get_journey` | Everyone | One case's ordered events, by business case id or stored hash, with its meta values, start/end and total duration. |
| `find_journey` | Everyone | Which project(s) hold a case id — searches every project on every connection you may query (or one connectionId), ready for get_journey. |
| `find_journeys` | Everyone | The individual cases behind an aggregate — slowest, longest or by step — with optional full path. Returned eventIds feed get_journey. |
| `get_notes` | Everyone | The notes on a project's steps and transitions — filter by severity, status and scope, optionally grouped; with a summary of counts. Times are local (Admin Console display zone) with the UTC offset. |
| `create_note` | Everyone — write | Create a note on a step (step) or a transition (fromStep + toStep). You become the author; id and time are set by the server. text required (≤ 4000), title ≤ 200, severity default NORMAL, scope default personal. Rate-limited per user. |
| `update_note` | Everyone — write | On a note you can see: add a comment (prepended to the thread, with an optional title), set status open/resolved; the author alone may change severity or scope. Existing text is never rewritten; a full thread (100,000 characters) takes no more comments. Rate-limited per user. |
| `compare_segments` | Power users & admins | Two slices of one project side by side: each segment's count, durations, goodness and end steps, then the biggest differences (B minus A) in end-step shares, transition times, transition frequency, and transitions found in only one segment. |
| `get_bottlenecks` | Power users & admins | Where time is lost: transitions by total waiting time (occurrences × average), the slowest typical transitions (median), rework (steps repeated in a journey) and self-loops. |
| `get_trend` | Power users & admins | The process over time: per day, week or month (by journey start) the journey count, average and median duration, and — with outcomeSteps — the reach rate of those steps. |
| `get_outcome_drivers` | Power users & admins | Why an outcome happens: the overall rate of reaching outcomeSteps, and the meta values and visited steps that raise or lower it (rate with / without, delta in percentage points, lift). Association, not cause. |
| `check_conformance` | Power users & admins | Test journeys against up to 10 rules — requires {step, ifStep?}, forbidden {step}, precedes {before, after}, max_duration {maxSecs}, max_gap {fromStep, toStep, maxSecs} — and count violations with example case ids. |

> The common filter: sampleSet (ORIGINAL | SAMPLE_1..3), fromDate / toDate (ISO dates), includedSteps (journeys visiting all of them), excludedSteps (journeys visiting none of them) — up to 200 step names each — and meta1 / meta2 / meta3 (up to 256 characters; case-insensitive substring match — see get_attribute_values). The per-journey power tools (bottleneck rework, trend, outcome drivers, conformance, end steps) keep whole journeys that are active in the date window rather than cutting them at its edges.

#### Discover

What exists: connections, projects, steps and attribute values.

**`list_connections`** — *Everyone.* Parameters: none.

*“Which Process Mining connections can I use?”*

```jsonc
// call
{
  "name": "list_connections",
  "arguments": {}
}
// result (excerpt; illustrative values)
[{"id": "7e31de50-…", "name": "02 - Air Travel", "schema": "PM_AIR", "comment": ""},
 {"id": "38891b38-…", "name": "03 - Finance", "schema": "PM_FIN", "comment": ""}]
```

**`list_projects`** — *Everyone.* Parameters: connectionId?, includeCounts?, sampleSet?.

*“Which process has the most journeys?”*

```jsonc
// call
{
  "name": "list_projects",
  "arguments": {
    "includeCounts": true
  }
}
// result (excerpt; illustrative values)
[{"connectionName": "02 - Air Travel", "projectId": 2,
  "title": "Airport Passenger Flow", "journeyCount": 148187},
 {"connectionName": "03 - Finance", "projectId": 1,
  "title": "Online Credit Application", "journeyCount": 20000}, …]
```

**`get_metadata`** — *Everyone.* Parameters: connectionId, projectId.

*“Show me all steps of the flight booking process.”*

```jsonc
// call
{
  "name": "get_metadata",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 5
  }
}
// result (excerpt; illustrative values)
{"metaTitles": {"meta1": "Journey Type", "meta2": "Airline", "meta3": "Payment Method"},
 "steps": ["Add Services", "Confirm Booking", …],
 "stepDetails": [{"step": "Confirm Booking", "description": "Booking confirmed and ticket issued",
                  "score": 15, "belongsTo": "Payment", "endOfProcess": true, "shape": "stadium"}, …],
 "dateRange": {"from": "2024-01-01T00:02:11", "to": "2024-12-31T23:51:40"}}
```

**`get_attribute_values`** — *Everyone.* Parameters: connectionId, projectId, meta? (meta1|meta2|meta3|all), limit? (50), filter.

*“Which payment methods occur in the bookstore?”*

```jsonc
// call
{
  "name": "get_attribute_values",
  "arguments": {
    "connectionId": "64254f7e-…",
    "projectId": 1,
    "meta": "meta1"
  }
}
// result (excerpt; illustrative values)
{"attributes": [{"meta": "meta1", "title": "Payment Method", "distinctValues": 3,
   "values": [{"value": "Credit Card", "journeys": 9120},
              {"value": "PayPal", "journeys": 6874},
              {"value": "Bank Transfer", "journeys": 4006}], "truncated": false}],
 "filterHint": "… case-insensitive and also matches substrings."}
```

#### Analyse

Aggregates over many journeys; every one takes the common filter.

**`get_process_map`** — *Everyone.* Parameters: connectionId, projectId, filter.

*“Draw the process map of the airport passenger flow.”*

```jsonc
// call
{
  "name": "get_process_map",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2
  }
}
// result (excerpt; illustrative values)
{"steps": {"ENTER Check-In": {"description": "Passenger checks in at the desk", "score": 0, …}, …},
 "transitions": [{"fromStep": "ENTER Check-In", "toStep": "LEAVE Check-In",
                  "occurrences": 44295, "avgSecs": 507.8, "medianSecs": 480.0, …}, …]}
```

**`get_transition_metrics`** — *Everyone.* Parameters: connectionId, projectId, filter.

*“How long does security take for passengers in 2024?”*

```jsonc
// call
{
  "name": "get_transition_metrics",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2,
    "fromDate": "2024-01-01",
    "toDate": "2024-12-31",
    "includedSteps": [
      "ENTER Security Check"
    ]
  }
}
// result (excerpt; illustrative values)
[{"fromStep": "ENTER Security Check", "toStep": "LEAVE Security Check",
  "occurrences": 145198, "avgSecs": 1020.0, "medianSecs": 1020.0,
  "minSecs": 240.0, "maxSecs": 1800.0, "stdDevSecs": 466.7}, …]
```

**`get_variants`** — *Everyone.* Parameters: connectionId, projectId, filter, limit?.

*“What are the three most common credit-application paths?”*

```jsonc
// call
{
  "name": "get_variants",
  "arguments": {
    "connectionId": "38891b38-…",
    "projectId": 1,
    "limit": 3
  }
}
// result (excerpt; illustrative values)
[{"path": "Bank -> Application Received -> Application Checked -> Credit Check -> Accepted -> …",
  "journeyCount": 4210, "stepCount": 7, "totalScore": 25}, …]
```

**`get_statistics`** — *Everyone.* Parameters: connectionId, projectId, filter.

*“How long do affiliate credit applications take?”*

```jsonc
// call
{
  "name": "get_statistics",
  "arguments": {
    "connectionId": "38891b38-…",
    "projectId": 1,
    "meta3": "Affiliate"
  }
}
// result (excerpt; illustrative values)
{"journeyCount": 9870,
 "durations": {"minSecs": 1804.0, "avgSecs": 201544.0, "medianSecs": 172800.0, …},
 "processGoodness": 3.41}
```

#### Cases

Individual journeys — find them, then open one.

**`get_journey`** — *Everyone.* Parameters: connectionId, projectId, eventId, sampleSet?.

*“Show me credit application CRA-000123.”*

```jsonc
// call
{
  "name": "get_journey",
  "arguments": {
    "connectionId": "38891b38-…",
    "projectId": 1,
    "eventId": "CRA-000123"
  }
}
// result (excerpt; illustrative values)
{"eventId": "CRA-000123", "storedEventId": "5e05bf5d94a6fb2c78e7722c3ec4b07b",
 "startDate": "2024-06-12T09:59:28", "endDate": "2024-06-12T11:01:11", "durationSecs": 3703.0,
 "meta": {"Applied Credit Sum": "> 25.000 EUR", "Income Class": "Low", "Channel": "Affiliate"},
 "events": [{"step": "Affiliate", "eventTime": "2024-06-12T09:59:28"}, …,
            {"step": "Rejected", "eventTime": "2024-06-12T11:01:11"}]}
```

**`find_journey`** — *Everyone.* Parameters: eventId, connectionId?, sampleSet?.

*“Where is case FLT-000124?”*

```jsonc
// call
{
  "name": "find_journey",
  "arguments": {
    "eventId": "FLT-000124"
  }
}
// result (excerpt; illustrative values)
{"eventId": "FLT-000124", "storedEventId": "69ab1ef5…",
 "matches": [{"connectionName": "02 - Air Travel", "projectId": 5,
              "title": "Flight Booking & Management", "startDate": "2024-10-30T23:22:09",
              "durationSecs": 1380.0, "stepCount": 14}],
 "searched": {"connections": 5, "projects": 8}}
```

**`find_journeys`** — *Everyone.* Parameters: connectionId, projectId, filter, orderBy?, limit? (20), min/maxDurationSecs?, min/maxSteps?, includePath?.

*“The five slowest orders that hit Payment Failed, with their paths.”*

```jsonc
// call
{
  "name": "find_journeys",
  "arguments": {
    "connectionId": "64254f7e-…",
    "projectId": 1,
    "limit": 5,
    "includedSteps": [
      "Payment Failed"
    ],
    "includePath": true
  }
}
// result (excerpt; illustrative values)
[{"eventId": "8c46773b…", "startDate": "2024-04-21T04:36:09", "durationSecs": 1134.0,
  "stepCount": 17, "meta": {"Payment Method": "Bank Transfer", …},
  "path": "Login -> Browse Catalog -> … -> Payment Failed -> Payment Retry -> …"}, …]
```

#### Notes

The human layer on the process. The two note-writing tools are the only writes on the MCP surface.

**`get_notes`** — *Everyone.* Parameters: connectionId, projectId, severity?, status?, scope?, groupBy?.

*“Show all closed notes, then all open notes, as separate groups.”*

```jsonc
// call
{
  "name": "get_notes",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2,
    "groupBy": "status"
  }
}
// result (excerpt; illustrative values)
{"total": 1, "summary": {"byStatus": {"open": 0, "resolved": 1}, …},
 "groupBy": "status",
 "groups": [{"key": "resolved", "count": 1, "notes": [{"id": "E422E185-…",
   "title": "A Note for testing", "severity": "URGENT", "status": "resolved",
   "scope": "shared", "author": "dirk.beerbohm", "target": "ENTER Check-In",
   "createdAt": "2026-09-23T12:34:45+02:00", "editedAt": "2026-09-23T12:36:42+02:00"}]}]}
```

**`create_note`** — *Everyone — write.* Parameters: connectionId, projectId, step | fromStep + toStep, text, title?, severity?, scope?.

*“Add a shared, important note on the security transition.”*

```jsonc
// call
{
  "name": "create_note",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2,
    "fromStep": "ENTER Security Check",
    "toStep": "LEAVE Security Check",
    "title": "Security wait",
    "text": "Median 17 min; peaks before 07:00.",
    "severity": "IMPORTANT",
    "scope": "shared"
  }
}
// result (excerpt; illustrative values)
{"created": true,
 "note": {"id": "9B1C…", "title": "Security wait", "severity": "IMPORTANT",
          "status": "open", "scope": "shared", "author": "dirk.beerbohm",
          "target": "ENTER Security Check → LEAVE Security Check", "targetType": "edge",
          "createdAt": "2026-09-24T08:15:02+02:00", "editedAt": null}}
```

**`update_note`** — *Everyone — write.* Parameters: connectionId, projectId, noteId, comment?, title?, status?, severity?, scope?.

*“Resolve the test note and say why.”*

```jsonc
// call
{
  "name": "update_note",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2,
    "noteId": "E422E185-0557-4E22-8DB2-BC62B30DA426",
    "comment": "Test complete.",
    "status": "resolved"
  }
}
// result (excerpt; illustrative values)
{"updated": true, "changes": ["comment", "status"],
 "note": {"id": "E422E185-…", "status": "resolved", "lastEditedBy": "dirk.beerbohm",
          "editedAt": "2026-09-24T08:16:40+02:00", …}}
```

#### Power analysis

Deeper analysis, reserved for users with the power-user role (and administrators). Anyone else gets a polite refusal naming the role.

**`compare_segments`** — *Power users & admins.* Parameters: connectionId, projectId, segmentA, segmentB (filter objects + label), limit? (10), minOccurrences? (30), sampleSet?.

*“How do Bank Transfer orders differ from PayPal orders?”*

```jsonc
// call
{
  "name": "compare_segments",
  "arguments": {
    "connectionId": "64254f7e-…",
    "projectId": 1,
    "segmentA": {
      "meta1": "Bank Transfer",
      "label": "Bank Transfer"
    },
    "segmentB": {
      "meta1": "PayPal",
      "label": "PayPal"
    }
  }
}
// result (excerpt; illustrative values)
{"segments": [{"label": "Bank Transfer", "journeyCount": 4006, …},
              {"label": "PayPal", "journeyCount": 6874, …}],
 "differences": {
   "endSteps": [{"step": "Payment Failed", "shareA": 0.12, "shareB": 0.03, "deltaPoints": -9.0}, …],
   "transitionTime": [{"fromStep": "Payment Processing", "toStep": "Payment Confirmed",
                       "avgSecsA": 5400.0, "avgSecsB": 45.0, "deltaSecs": -5355.0}, …],
   "transitionFrequency": […], "onlyInA": […], "onlyInB": […]}}
```

**`get_bottlenecks`** — *Power users & admins.* Parameters: connectionId, projectId, filter, limit? (10), minOccurrences? (30).

*“Where do credit applications lose the most time?”*

```jsonc
// call
{
  "name": "get_bottlenecks",
  "arguments": {
    "connectionId": "38891b38-…",
    "projectId": 1
  }
}
// result (excerpt; illustrative values)
{"totalWaitSecs": 3.1e9,
 "byTotalWaitTime": [{"fromStep": "Credit Check", "toStep": "Senior Agent Approval",
   "occurrences": 6120, "avgSecs": 87942.0, "totalWaitSecs": 538205040.0,
   "shareOfWaitTime": 0.17}, …],
 "slowestTypicalTransitions": […],
 "rework": [{"step": "Application Checked", "journeys": 5230, "extraVisits": 5890}, …],
 "selfLoops": […]}
```

**`get_trend`** — *Power users & admins.* Parameters: connectionId, projectId, filter, granularity? (day|week|month), outcomeSteps?, limit?.

*“Is the denied-boarding rate changing month by month?”*

```jsonc
// call
{
  "name": "get_trend",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 2,
    "granularity": "month",
    "outcomeSteps": [
      "DENIED Boarding Dom",
      "DENIED Boarding Int"
    ]
  }
}
// result (excerpt; illustrative values)
{"granularity": "month",
 "periods": [{"period": "2024-01-01", "journeys": 12530, "avgDurationSecs": 4210.0,
              "medianDurationSecs": 4080.0, "outcomeJourneys": 598, "outcomeRate": 0.0477}, …]}
```

**`get_outcome_drivers`** — *Power users & admins.* Parameters: connectionId, projectId, filter, outcomeSteps, minSupport? (30), limit? (10).

*“What makes a credit application end in Rejected?”*

```jsonc
// call
{
  "name": "get_outcome_drivers",
  "arguments": {
    "connectionId": "38891b38-…",
    "projectId": 1,
    "outcomeSteps": [
      "Rejected"
    ]
  }
}
// result (excerpt; illustrative values)
{"journeys": 20000, "outcomeJourneys": 5400, "outcomeRate": 0.27,
 "raisesOutcome": {"attributes": [{"title": "Income Class", "value": "Low",
     "outcomeRate": 0.61, "rateWithout": 0.16, "deltaPoints": 34.0, "lift": 2.26}, …],
   "steps": […]},
 "lowersOutcome": {"attributes": […], "steps": […]}}
```

**`check_conformance`** — *Power users & admins.* Parameters: connectionId, projectId, filter, rules, examples? (5).

*“Is payment always processed before a booking is confirmed, within 5 minutes?”*

```jsonc
// call
{
  "name": "check_conformance",
  "arguments": {
    "connectionId": "7e31de50-…",
    "projectId": 5,
    "rules": [
      {
        "type": "precedes",
        "before": "Process Payment",
        "after": "Confirm Booking"
      },
      {
        "type": "max_gap",
        "fromStep": "Process Payment",
        "toStep": "Confirm Booking",
        "maxSecs": 300
      }
    ]
  }
}
// result (excerpt; illustrative values)
{"journeysChecked": 20000,
 "rules": [{"type": "precedes", "rule": "'Process Payment' must happen before 'Confirm Booking'",
            "violations": 0, "violationRate": 0.0, "conformanceRate": 1.0, "exampleEventIds": []},
           {"type": "max_gap", "violations": 0, …}]}
```
<!-- MCP-TOOL-REFERENCE:END -->

### More on some of the tools

**`list_projects` across connections.** `connectionId` is optional: omit it and the tool
returns every project on every connection assigned to you, each entry tagged with its
`connectionId` and `connectionName`. Add `includeCounts: true` for a `journeyCount` per
project (one count query each), which answers "which process has the most journeys?" in a
single call. A connection that cannot be opened yields one entry carrying `error` instead
of a project, so one unreachable database does not fail the whole listing.

**`find_journeys` — from the aggregate to the cases.** Every other tool summarises many
journeys; `get_journey` needs a case id you already have. `find_journeys` closes the gap:
it returns one row per case (stored id, start/end, duration, step count, meta attributes)
for any filter, ordered by `orderBy` — `DURATION_DESC` (the default, slowest first),
`DURATION_ASC`, `START_DESC`, `START_ASC`, `STEPS_DESC`, `STEPS_ASC`. It also takes
`limit` (default 20), `minDurationSecs` / `maxDurationSecs`, `minSteps` / `maxSteps`, and
`includePath` to add each journey's full step path. The returned `eventId` is the stored
MD5 — `JOURNEYS` never holds the plaintext business id — and `get_journey` accepts it
as-is, so the drill-down is: `get_statistics` → `find_journeys` → `get_journey`.


**`get_notes` — the annotations on a process.** Steps and transitions can carry notes
(issues, observations, review comments) with a **severity** (`NORMAL`, `INFO`, `IMPORTANT`,
`URGENT`), a **status** (open / resolved) and a **scope** (a private *personal* note, or a
*shared* one visible to everyone). `get_notes` returns them for a project, filterable by any
of those, and optionally **grouped** (`groupBy`: `severity` | `status` | `scope` | `target`).
Visibility matches the app exactly — you see shared notes plus your own, never another
user's private notes — and every response carries a `summary` with per-severity, per-status
and per-scope counts.


---

## Prerequisites

- An **Authentik** server reachable from the Process Mining host (this guide assumes
  `https://authentik.example.com:19443`).
- Administrator access to both Authentik and the Process Mining admin console.
- Each MCP user must **already exist and be enabled** in Process Mining (Users tab) with the
  **same username** the token will carry (see “username claim” below), and must be
  **assigned the connection(s)** they should query (Database Connections tab).

---

## Part A — Configure Authentik

1. **Create an OAuth2/OpenID Provider**
   *Applications → Providers → Create → OAuth2/OpenID Provider.*
   - **Name**: `Process Mining MCP`.
   - **Authorization flow**: your standard `default-provider-authorization-explicit-consent`
     (or implicit-consent).
   - **Client type**: `Public` (recommended for interactive clients that use PKCE) — or
     `Confidential` if your client stores a secret.
   - **Redirect URIs**: add the callback(s) your client uses. For **Claude** these are:
     - `https://claude.ai/api/mcp/auth_callback`
     - `https://claude.com/api/mcp/auth_callback`
     - and, for Claude Desktop, a local loopback such as `http://localhost:*` (use the exact
       value Claude shows you if it differs).
   - **Signing Key**: pick an RSA key (the access token is then a signed RS256 JWT the MCP
     server can verify offline). Note the key.
   - **Scopes**: include `openid`, `profile`, `email` (add `offline_access` if you want
     refresh tokens).
   - Save, then open the provider and note its **Client ID** (and secret, if confidential).

2. **Create an Application** bound to that provider
   *Applications → Applications → Create.*
   - **Name**: `Process Mining MCP`, **Slug**: e.g. `process-mining-mcp`.
   - **Provider**: the provider from step 1.
   - Under **Policy / Group / User Bindings**, restrict who may use it (e.g. bind a group
     `process-mining-users`). You can enforce the same group again in the MCP server settings.

3. **Note the endpoints.** With the slug above, Authentik publishes (all under
   `https://authentik.example.com:19443/application/o/process-mining-mcp/`):
   - **Issuer**: `.../application/o/process-mining-mcp/`
   - **Discovery**: `…/.well-known/openid-configuration`
   - **JWKS**: `…/jwks/`

   > **Access-token audience (strongly recommended).** Authentik's access token may not set
   > `aud` to your client id unless you add an audience via a scope/property mapping. Adding
   > that mapping and setting the client id as the MCP **Audience** is the recommended setup:
   > it ties each token to *this* application, so a token minted for a different app on the
   > same Authentik can't be replayed against the MCP server. If you leave **Audience** blank
   > the `aud` check is skipped — any validly-signed token from the issuer is accepted (still
   > gated by the issuer, signature, user-mapping and optional group checks), so prefer setting
   > it whenever the same Authentik serves more than one application.

   > **Dynamic Client Registration (DCR).** Some clients register themselves automatically.
   > If yours does and you prefer that, enable DCR in Authentik; otherwise the manual
   > provider above is all you need and you give the client the Client ID directly.

---

## Part B — Configure the MCP server (admin console)

1. Open the admin console → **MCP Server** tab.
2. Fill in **Authentik (OAuth) settings**:
   - **Issuer URL** — `https://authentik.example.com:19443/application/o/process-mining-mcp/`
   - **JWKS URL** — leave blank to auto-discover from the issuer, or paste `…/jwks/`.
   - **Audience / Client ID** — the client id, once you've configured the token's `aud`
     (recommended). Blank skips the `aud` check and accepts any token from the issuer.
   - **Required group** — optional; only members of this Authentik group may connect
     (matched against the token's `groups` claim).
   - **Username claim** — the JWT claim matched (case-insensitively) to a Process Mining
     username. Default `preferred_username`; use `email` if your usernames are email
     addresses.
3. Press **Save settings**, then **Test Authentik** — it fetches the discovery document and
   JWKS and reports the signing-key count. Fix any error before continuing.
4. Tick **Enable the MCP server**. (Enabling/disabling is immediate; no restart.)

> **TLS.** The server follows the same TLS mode and certificate as the app and admin console.
> Turn TLS on in the **TLS / SSL** tab and use the **HTTPS** endpoint (`:18493`) — OAuth
> clients require HTTPS. A TLS change takes effect after **↻ Restart app server** (App Control).

---

## Behind a reverse proxy

The MCP server listens on its own port (container `8130`/`8493`, host `18130`/`18493`). If you
expose it under a public domain path — e.g. `https://pm.example.com/mcp` — the proxy must:

1. **Preserve the path.** Forward `/mcp` to the backend as `/mcp`, not stripped to `/`. In
   nginx, `proxy_pass http://mcp-backend:8493;` (no trailing slash) preserves it;
   `proxy_pass http://mcp-backend:8493/;` (trailing slash) **strips** the prefix and the
   backend then sees `/` (you'd get a `404 {"detail":"Not Found"}`). The server also answers
   at the root as a fallback, so a stripping proxy still works — but preserving the path is
   cleaner. Route `/mcp`, `/.well-known/oauth-protected-resource` (and its `…/mcp` suffix) and
   `/health` to the backend.
2. **Send forwarding headers.** Set `X-Forwarded-Proto` and `X-Forwarded-Host` so the OAuth
   discovery document advertises the public `https://pm.example.com/mcp`, not the internal
   host:port.

Example nginx:

```nginx
location /mcp {
    proxy_pass https://127.0.0.1:18493;   # no trailing slash — keep the /mcp path
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
}
location = /.well-known/oauth-protected-resource      { proxy_pass https://127.0.0.1:18493; proxy_set_header X-Forwarded-Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
location = /.well-known/oauth-protected-resource/mcp  { proxy_pass https://127.0.0.1:18493; proxy_set_header X-Forwarded-Host $host; proxy_set_header X-Forwarded-Proto $scheme; }
```

Point the client at the public URL (`https://pm.example.com/mcp`). Alternatively, skip the
proxy and expose the MCP port directly (`https://<host>:18493/mcp`) if your firewall allows it
and TLS is enabled in the admin console.

---

## Part C — Add the server to an AI client

### Claude (claude.ai / Claude Desktop)

1. **Settings → Connectors → Add custom connector**.
2. **Name**: `Process Mining`. **URL**: `https://<your-host>:18493/mcp`.
3. Save and click **Connect**. Claude discovers Authentik from the server's
   `/.well-known/oauth-protected-resource` document, opens Authentik's sign-in, and (after you
   approve) stores the token. The Process Mining tools then appear in the connector.
4. In a chat, enable the connector and ask e.g. *“list my process-mining connections”*, then
   *“show the process map for project 1 on connection c1”*.

The same pattern applies to any MCP client that supports **remote (HTTP) servers with OAuth**:
point it at `https://<your-host>:18493/mcp`.

---

## Verifying by hand

Discovery (no auth):

```bash
curl -k https://<your-host>:18493/.well-known/oauth-protected-resource
```

A call with a token you already obtained from Authentik:

```bash
curl -k -X POST https://<your-host>:18493/mcp \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "arguments":{},"params":{"name":"list_connections","arguments":{}}}'
```

`GET /health` (unauthenticated) returns `{"ok":true,"enabled":<bool>}`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `503 The MCP server is disabled` | Enable it in the admin MCP tab. |
| `401` + a `WWW-Authenticate` header | No/invalid token — the client should run the OAuth flow. Check the issuer/JWKS in the MCP tab and press **Test Authentik**. |
| `403 No enabled Process Mining user matches '…'` | The token's username claim doesn't match an enabled PM user. Create the user (Users tab) with that exact name, or change the **Username claim** (e.g. to `email`). |
| `403 …not in the group required` | The user isn't in the configured **Required group** in Authentik. |
| `Connection … is not assigned to you` | Assign the connection to the user (Database Connections tab). |
| `Sorry — … reserved for power users` | The user lacks the power-user role. Grant it in the admin console (Users tab → **Make power**) if they should run the deeper-analysis tools. |
| `You have reached the limit of N note changes per minute` | A client is writing notes in a loop. Wait a minute; raise `PMW_MCP_NOTE_WRITES_PER_MIN` only if the volume is intended. |
| `Step '…' does not exist in project …` (create_note) | Step names must match exactly — list them with `get_metadata`. |
| `This note's thread is full` | The note's thread reached 100,000 characters. Start a new note for the follow-up. |
| `A batch may hold at most 20 messages` | The client sent a JSON-RPC batch of more than 20 calls; split it. |
| `includedSteps must be a list of at most 200 step names` | Filters are bounded (200 steps per list, meta values 256 characters). |
| Test says it can't reach Authentik | Wrong issuer URL or the host can't reach `:19443`. The server does not verify Authentik's TLS certificate (internal host), but the URL and network path must be right. |

## Security notes

- Tokens are verified **cryptographically** against Authentik's JWKS (RS256); only the JWKS
  **transport** skips certificate verification (Authentik is a trusted internal host), which
  does not weaken token integrity.
- The MCP server never exposes more than the mapped user's assigned connections — the same
  boundary as the app. Its only writes are notes (`create_note` / `update_note`), under the
  app's own note rules, with server-side validation, a per-user rate limit and an audit
  entry per write (see *What the server exposes*). Every other tool is read-only.
- The deeper-analysis tools are gated on the **power-user** role (administrators included);
  the role is re-read from the user store on every request, so revoking it takes effect at once.
- Configure `PMW_MCP_MAX_ROWS` (default 1000) to cap rows returned per call,
  `PMW_MCP_JWKS_CACHE_SECS` (default 3600) for how long signing keys are cached, and
  `PMW_MCP_NOTE_WRITES_PER_MIN` (default 20) for the per-user note-write limit. Filters are
  bounded (200 step names per list, meta values 256 characters) and a JSON-RPC batch may hold
  at most 20 messages, so one request cannot build an unbounded query.
