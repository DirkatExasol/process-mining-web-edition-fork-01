# Process Mining Demonstrator — Web Migration Architecture

Port of the macOS/SwiftUI **Process Mining Demonstrator** to a web application.

Source of truth for behaviour:
`/Users/dirk/Work/Swift/Projects/Process Mining Demonstrator/Process Mining Demonstrator/Process Mining Demonstrator/*.swift`

## Goals

1. Functional parity with the Swift app.
2. Look-and-feel parity: left sidebar with the same collapsible sections, same
   KPI strip, same chart modes, same interactions (drag nodes, collapse groups,
   pan/zoom, valve-synced A/B panels, sticky notes on nodes/edges).
3. Flow charts rendered with **ReactFlow** (`@xyflow/react`, MIT / non-Pro only).
4. Python implementation, split into two processes:
   - **Compute Backend** (FastAPI, port **8000**) — Exasol access, analytics,
     simulation, sampling, LLM proxy, settings persistence.
   - **GUI Server** (FastAPI, port **8080**) — serves the React SPA and proxies
     `/api/*` to the compute backend.

## Process split

```
Browser ──► GUI Server (:8080)  ──proxy /api──►  Compute Backend (:8000) ──► Exasol
              static SPA                              pyexasol / openai
```

Rationale: the browser only ever talks to the GUI server, so the compute backend
can live on a different host / network segment close to the database.

## Directory layout

```
Process_Mining_Web/
├── .venv/                     Python 3.13 virtualenv
├── ARCHITECTURE.md            this file
├── README.md
├── requirements.txt
├── run.sh                     start both servers
├── backend/                   Compute Backend
│   └── app/
│       ├── main.py            FastAPI app + routers
│       ├── config.py          settings (ports, data dir, secret key)
│       ├── models.py          pydantic mirrors of Models.swift
│       ├── chart_state.py     DetailViewMode / ChartFilterState mirrors
│       ├── db/
│       │   ├── manager.py     Exasol connection manager (DatabaseManager.swift)
│       │   └── repository.py  all SQL (ProcessRepository.swift)
│       ├── services/
│       │   ├── simulation.py  Markov Monte-Carlo (SimulationEngine.swift)
│       │   ├── sampling.py    random / temporal / path-diverse
│       │   ├── conformance.py happy-path coverage + process goodness coverage
│       │   ├── similarity.py  A/B Q-metric
│       │   ├── llm.py         OpenAI-compatible chat (LLMService.swift)
│       │   ├── docgen.py      AI documentation prompt + summaries
│       │   └── backup.py      AES-256-GCM backup/restore (BackupManager.swift)
│       ├── store/
│       │   └── settings.py    SQLite key/value "UserDefaults" + secret vault
│       └── api/               routers, one per feature area
├── frontend/                  GUI Server
│   ├── server.py              static + proxy
│   └── web/                   Vite + React + TypeScript SPA
└── data/                      runtime state (sqlite, secret key) — gitignored
```

## Persistence mapping

| Swift | Web |
|---|---|
| `UserDefaults` (settings, filter groups, happy paths, norms, KPI order, layouts) | SQLite `kv` table in the compute backend, namespaced identically to the Swift keys |
| Keychain (DB passwords) | SQLite `secrets` table, values encrypted with Fernet; key file `data/secret.key`, mode 0600 |
| `@AppStorage` UI prefs | same SQLite `kv` store, read/written through `/api/settings` and mirrored into a React context |

Key names are kept **byte-identical** to the Swift ones so a Swift JSON backup
can be restored into the web app and vice versa:
`filterGroups_<projectId>`, `happyPaths_<projectId>`, `norms_<projectId>`,
`norms_metric_<projectId>`, `llm_prompt_<projectId>`, `layout_<projectId>_<chartMode>`,
`graph.collapsedGroups_<projectId>_<chartMode>`, `kpi.order`, `kpi.show.*`,
`sampling.method.<SET>.<projectId>`, `processmap.*`, `graph.*`, `slider.mode`,
`app.theme`, `security.requireAuthentication`, `database_servers`, `llm_servers`,
`connection_profiles`, `active_profile_id`.

## Database schema (unchanged, read from Exasol)

`PROJECTS`, `JOURNEYS`, `STEPS`, `METAS` required; `NOTES` auto-created;
`JOURNEYS.SAMPLE_SET` auto-added for sampling.

## Chart modes (DetailViewMode)

`A-Chart`, `B-Chart`, `A/B Comparison`, `Individual Journey`,
`AI supported Documentation`, `Statistics`, `Conformance Check`, `Happy Path`,
`Notes`, `Simulation`.

## Layout algorithm (FlowChartView.swift → frontend/web/src/graph/layout.ts)

Ported verbatim so node placement matches the Swift app:

- constants `nodeW=198, nodeH=63 (77 when steps carry timestamps), hGap=56, vGap=88, padding=48, gridSize=20`
- greedy DAG construction (edges by descending occurrences, skip cycle-creating)
- Kahn longest-path layering
- Sugiyama barycenter crossing minimisation, 3 alternating passes
- layer rows centred horizontally on the canvas
- `BELONGS_TO` group box overlap resolution (pad 20, labelPad 18, minGap 24, 30 iterations)

Rendered with ReactFlow: custom node type `stepNode` (stadium / round / hex /
circle, bg/fg colour, score badge, end-of-process dot, note badge, description
or timestamp sub-line), custom edge type `metricEdge` (bezier, width
`3 + ratio*19`, alpha `0.3 + ratio*0.5`, gradient colour per `EdgeColorSchema`,
centre label / norm badge, note dot), plus group boxes as non-selectable
background nodes and start/end arrow decorations.

## KPI tiles

Ordered by `kpi.order`, each toggled by `kpi.show.<id>`:
`totalJourneys, filteredJourneys, shortestJourney, avgJourney, stdDev,
longestJourney, graphValue, processGoodness, processSimilarity, activeSample`.

## Formulas ported

- **Process Goodness**: `Σ_path (freq/total) * (totalScore/√stepCount − 0.01*avgDuration)`
  then `× (filteredCount / totalJourneyCount)^0.5`.
- **Happy-path conformance**: journey-count-weighted max edge-coverage over branches.
- **A/B similarity Q**: `0.4*Q_var + 0.4*Q_nodes + 0.2*Q_cov` (see AppViewModel).
- **Simulation**: start steps where `inDeg/outDeg < 0.2` on the *original* graph,
  BFS pruning, lognormal edge durations via Box–Muller, min 60 s, Poisson arrivals.

## API surface (compute backend)

```
GET    /api/health
# connections
GET/POST/PUT/DELETE /api/servers/db        DatabaseServer CRUD (+ password)
GET/POST/PUT/DELETE /api/servers/llm       LLMServer CRUD
GET/POST/PUT/DELETE /api/profiles          ConnectionProfile CRUD
POST   /api/profiles/{id}/connect
POST   /api/disconnect
GET    /api/connection/status
POST   /api/servers/db/test
POST   /api/servers/llm/test
# project data
GET    /api/projects
GET    /api/projects/{pid}/bootstrap       steps, metas, bounds, totals
POST   /api/projects/{pid}/graph           filtered graph + counts + durations + goodness
POST   /api/projects/{pid}/journey-paths   variants
POST   /api/projects/{pid}/statistics      buckets + time series + graph + paths
GET    /api/projects/{pid}/journey/{eid}   individual journey graph
GET    /api/projects/{pid}/event-ids       autocomplete
PUT    /api/projects/{pid}/steps/{step}    step editor
# notes / sampling / simulation / llm / settings / backup
```

## Build / run

```
./run.sh                 # both servers
backend :8000  frontend :8080
```
