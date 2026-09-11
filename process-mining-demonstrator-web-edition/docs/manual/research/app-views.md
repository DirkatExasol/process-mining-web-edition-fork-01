# Process Mining Demonstrator — Web Edition: Main-App Views & Chart Modes (documentation-grade notes)

Source: `/Users/dirk/Work/Process_Mining_Web/frontend/web/src` — `App.tsx`, `views/`, `flow/`, `components/KpiStrip.tsx`, `components/JourneyTimeSlider.tsx`, `components/NoteEditor.tsx`, `components/Markdown.tsx`, plus `types.ts`, `settings.ts`, `store.ts`, `graph/colors.ts`, `graph/format.ts` for labels/defaults.

---

## 1. Application shell and the detail pane (right-hand area)

- Layout: left **Sidebar** (collapsible) + right **detail pane**. When the sidebar is hidden, a floating **▤** button (tooltip/aria-label "Show sidebar") appears top-left of the detail pane to restore it.
- **Title capsule** (top of detail pane): shows the selected project's title (falls back to "Process Map" when no project is selected) and, underneath, the name of the active view mode (invisible until a project is selected).
- **Toolbar** (top-right):
  - **？** button (tooltip "Help") — opens the floating Help panel. Keyboard shortcut: **⌘/Ctrl + /** or **⌘/Ctrl + ?** toggles Help.
  - **☰ \<mode icon\>** button (tooltip "Switch view") — only shown when connected AND a project is selected. Opens a popover menu of view modes; the current mode shows a ✓ check. Clicking outside closes it.
- **Startup states**: while booting the app shows a large spinner with "Starting…". If the admin requires login and there is no session, the Login view is shown instead of the app (also kept up during forced-2FA enrolment until recovery codes are shown). A **legal gate** must be accepted before the app UI appears; declining it signs the user out (returns to Login).
- **Alerts**: modal alert boxes (title + message + primary/secondary buttons) appear centered over a scrim; clicking the scrim dismisses.
- **Theme**: setting `app.theme` (default `system`) — follows OS dark/light when "system".

### View modes (menu order, icons, roles)

| Mode | Icon | Role restriction |
|---|---|---|
| A-Chart | 📈 | all users |
| B-Chart | 📉 | all users |
| A/B Comparison | ⇄ | all users |
| Individual Journey | 🧍 | all users |
| AI supported Documentation | 🧠 | all users |
| Statistics | 📊 | all users |
| Conformance Check | 🛡️ | **power users and admins only** (hidden from plain users) |
| Happy Path | 🪧 | **power users and admins only** |
| Notes | 🗒️ | all users |
| Simulation | 🎲 | **power users and admins only** |

- Global not-connected state (any mode): glyph ⛁, title **"Not Connected"**, text "Add a connection in the sidebar and tap it to connect to your Exasol database."
- **Per-mode filter memory**: each view mode remembers its own filter state (dates, included/excluded steps, meta filters, metric). Switching modes saves the current state and restores the target mode's state. Exceptions: **Statistics always inherits the A-Chart's filter state**; A/B Comparison maps to the saved A-Chart/B-Chart states (active side starts as A). Switching to A-Chart, B-Chart, A/B Comparison, AI supported Documentation or Notes also reloads the notes list.
- On first project load, the A-Chart loads immediately with the default window; every other mode is seeded with the same window and the project's real filter bounds.

---

## 2. KPI strip (shared header for A-Chart, B-Chart, Individual Journey)

Shown only when connected + project selected + data present (for Individual Journey: when a journey date is loaded). Modes that render their own header instead: A/B Comparison, Statistics, Notes, AI supported Documentation, Happy Path, Conformance Check, Simulation.

- **KPI handle** (collapse/expand bar): chevron toggles the strip; state persists in setting `processmap.kpiExpanded` (default expanded). When collapsed it shows a summary: "`<filtered>` / `<total>` Journeys" (e.g. "1,234 / 10,000 Journeys").
- **Transitions-mode pill** (right side of the handle; not shown in Individual Journey):
  - **⚡ Pre-materialized** — tooltip: "Transitions are read from the pre-materialized TRANSITIONS_RAW table."
  - **↻ Live query** — tooltip: "Transitions are computed live from the event log on each load."
  - **⚠ Live (not built)** — tooltip: "Pre-materialized transitions are enabled for this connection, but TRANSITIONS_RAW is not built yet — running the live query meanwhile. Rebuild it in the admin interface (Connections → Rebuild now)."

### Standard KPI tiles

Order and visibility are user-configurable (sidebar Config → KPIs). Settings: `kpi.order` (default order below) and `kpi.show.<id>` (all default **on**). Values show "—" when unknown; a small spinner while loading.

| id | Label | Icon | Value / meaning |
|---|---|---|---|
| totalJourneys | **Total Journeys** | 👥 | Unfiltered journey count of the project |
| filteredJourneys | **Filtered Journeys** | ⛃ | Journeys matching current filters |
| shortestJourney | **Shortest Journey** | 🐇 | Min journey duration (formats: "< 60 s" → "N s", then "N.n min", "N.n h", "N.n d") |
| avgJourney | **Avg Journey** | ⏱️ | Mean journey duration |
| stdDev | **Std Dev** | 〰️ | Std deviation of journey durations |
| longestJourney | **Longest Journey** | 🐢 | Max journey duration |
| graphValue | **Graph Value** | ƒ | Σ (step score × visits) over scored nodes; visits = max(incoming, outgoing) occurrences. Signed with explicit +/−. Hidden entirely if no step carries a score. |
| processGoodness | **Process Goodness** | ◔ | Server-computed goodness score, shown signed with 2 decimals. Hidden if null. In A/B mode the tile is tinted green (better than other side), red (worse), blue (equal within 0.005). |
| processSimilarity | **Process Similarity** | ⇄ | A/B similarity 0–1 (2 decimals); green ≥ 0.7, red ≤ 0.3, blue between. Only present when an A/B similarity has been computed. |
| activeSample | **Active Sample** | ▤ | Label is the side's data source: "Original" / "Sample 1..3", or "Sim-A"/"Sim-B" when a simulation is the data source; value = journey count of that source. |

### Individual-Journey KPI strip (replaces the standard tiles)

- **Date** 📅 — journey start date (short format).
- **Duration** ⏱️ — end − start of the journey.
- **Sum of Scores** ƒ — sum of step scores across visited steps (signed; "—" if no scores).
- **Steps visited / distinct** ⑂ — "`<total>` / `<distinct>`" where total = transitions traversed + 1.
- Up to three extra 🏷 tiles for the project's meta fields (label = project's meta1/2/3 title, value = the journey's meta value) — only when both title and value exist.

---

## 3. The process flowchart canvas (used by A-Chart, B-Chart, A/B panels, Happy Path left pane, Conformance, Individual Journey, Simulation "Flow" tab)

### Nodes
- Each process step is a colored node. Shape comes from the step definition: `stadium` (default, pill), `round` (12 px corner), `circle`, `hex` (flat-top hexagon). Background/foreground colors are per-step (named SwiftUI colors or 6-digit hex; unknown values fall back to the accent blue).
- Node content: step name; if the step carries an event time (Individual Journey) the time (HH:MM:SS, 24 h) is shown under the name; else if "Show node descriptions" is on and the step has a description differing from its name, a truncated description (20 chars + …) is shown under the name. Hover tooltip shows the full description (or the name).
- **Badges** on a node: an orange **end-of-process** dot (steps flagged endOfProcess); a **score** badge showing the step's score (green > 0, red < 0, blue = 0); a **yellow ✎ note badge** when the node has notes (tooltip "This node has notes").
- **Start/end markers**: a green downward arrow (dot + stem + head) *above* every node with no incoming transitions (process start); an orange one *below* every node with no outgoing transitions (process end). When grouping boxes are shown, markers clear the box.
- **Node click** opens a context popover titled with the step name:
  - **✓ Require in journeys** — adds the step to the "included steps" filter (removing it from excluded) and reloads the graph.
  - **⊖ Exclude from journeys** (red) — adds to excluded (removing from included) and reloads.
  - **≡ Show description** — only when node descriptions are enabled and a real description exists; opens a centered popover with the step name, full description text, and a **Done** button.
  - **✎ Show Notes (N)** (yellow) — opens the note flow (see §14); N = number of notes on this node.
  - On a **read-only source (simulation output)** the Require/Exclude items are hidden — only description/notes remain.
- **Dragging**: nodes snap to a 20 px grid; positions persist per project *and* per chart mode (A-Chart, B-Chart, HappyPath, Conformance, `sim_<slot>`, `ij_<eventId>` each keep independent layouts). Writes to storage happen only on release.

### Groups (BELONGS_TO)
- When "Show grouping" is on (setting `processmap.showGrouping`, default on), steps sharing a BELONGS_TO value are surrounded by a dashed tinted box with a colored **name pill** (deterministic per-group hue) and a round **collapse toggle** at its top-right: red **−** = collapse (tooltip "Collapse \<group\>"), green **+** = expand (tooltip "Expand \<group\>").
- **Collapsed group** renders as a single accent-colored proxy node showing the member count ("N nodes"). Edges to/from members are merged: **connection counts are summed, times are weighted-averaged, intra-group edges are dropped** — a grey hint at the bottom-center of the canvas reads: "Collapsed groups: connection counts summed · times weighted-averaged". Min/Max/StdDev values are unavailable on merged edges (label shows "—" for those metrics).
- Dragging the **box** moves all member nodes together (or the proxy when collapsed).
- **Initial collapse state** per project follows setting `graph.startMode` (default `expanded`): `expanded` = all open, `collapsed` = all collapsed, `persisted` = restore the last state per project + chart mode.
- Zoom control extra button (only when grouping is on and groups exist): **⤡ Collapse all groups** / **⤢ Expand all groups** (toggles based on current state).

### Viewport & zoom controls (bottom overlay)
- **−** (Zoom out, ÷1.3), **percentage readout** (e.g. "100%"), **+** (Zoom in, ×1.3), **⤢** (Fit to view), separator, **↺** (Reset node layout — clears all manual drag positions and re-fits). Zoom clamps 15 %–500 %. **Double-click** anywhere on the canvas also fits to view. Background: dotted grid.
- Loading overlay: a small pill "Loading…" with a spinner while a reload is in flight (chart stays interactive).
- **Notice** (red text, top-right of canvas): shown for simulation-sourced charts — "Sim-A: simulation data is read-only — interactive filtering, drill-down and step editing are not available." (or Sim-B).

### Display-scaling settings (sidebar Config → Fonts, read by the canvas)
- `graph.node.scale` (default **2.25**) — grows the node box *and* its font together, so text never spills.
- `graph.edge.scale` (default **3.375**) — sizes edge labels/badges and the note bubbles on edges.
- `graph.group.scale` (default **2.25**) — sizes the group name pill and its collapse toggle.
- `graph.optimisedLayout` (default **on**) — optimised auto-layout.
- `processmap.showNodeDescriptions` (default **on**).

### Colour-scale legend & Edge Colour Wizard
- When "Colorise edges by weight" is on (`graph.edge.colorizeByWeight`, default **on**), a legend card floats on the canvas: the current metric name, a ⚙ icon, a Low→High gradient bar (or "No color scale" for the neutral schema). **Clicking the legend opens the Edge Colour Schema wizard** (tooltip "Configure edge colour schema per metric").
- **Edge Colour Schema sheet** (🎨): explanatory text "Edge thickness always encodes the selected metric. When colouring is on, each transition is tinted along the chosen gradient from the lowest to the highest value. Settings are saved per metric." Contains the global **"Colorise edges by weight"** switch, then one row per metric (Count, Avg Time, Min Time, Max Time, Std Dev) with a schema dropdown and a live gradient preview. Footer: **Reset to defaults** (restores per-metric defaults) and **Done**.
- Schema options and defaults:

| Schema option (label) | Notes |
|---|---|
| None (grey) | flat grey, no scale |
| Green (high is good) | red → green; **default for Count** |
| Red (low is good) | green → red; **default for Max Time** |
| Blue scale | light → dark blue; **default for Min Time** |
| Orange scale | light → dark orange; **default for Avg Time** |
| Purple scale | light → dark purple; **default for Std Dev** |

Settings persist per metric under `graph.edge.colorSchema.<metric>` and survive backups.

---

## 4. Edges: metrics, thickness, labels

- **Metrics** (five, shown as chips with icons): `# Count`, `⏱ Avg Time`, `⌄ Min Time`, `⌃ Max Time`, `〰 Std Dev`.
- **Thickness & opacity encode the metric value**: width 3–22 px and alpha 0.3–0.8, linear in value ÷ max value across visible edges. Colour follows the metric's gradient (when colourising is on), else grey. Arrowhead scales with width.
- **Edge label**: Count → compact count ("1.2k", "3.4M"); time metrics → "Ns" / "Nm" / "N.nh" / "N.nd"; missing time value → "—". Tooltip on the label: "`<from>` → `<to>` · `<occurrences>`".
- **Self-loops** (step → itself) render as a circle above the node (no arrowhead).
- **Yellow ✎ bubble** next to the label when the transition has notes (tooltip "This transition has notes").
- **Edge click** (edge line has a wide invisible hit area; the label is clickable too): in normal charts opens a popover titled "`<from>` → `<to>`" with **✎ Show Notes (N)**; in Conformance edit mode it opens the norm editor instead (§10).
- **Conformance overlays** (Conformance view only): in *view* mode edges are colored green (compliant) / red (violation) / grey (no norm) with width by actual value, and the label is a solid badge with the actual value; in *edit* mode all edges are uniform grey width 6 and the badge shows the stored norm ("—" if none; badge accent-colored when a norm exists, faint grey otherwise). For Count the values are percentages of the source node's outgoing flow ("42%").
- **Individual Journey playback**: a single blue dot with white outline travels the edges one after another in chronological order (0.8 s per edge, endless loop) — the dot "hops" edge to edge in the order the steps occurred.

---

## 5. "Date & Metrics" controls card (A-Chart, B-Chart, each A/B panel)

Collapsible card above the chart; expansion persists per surface (`achart.controlsExpanded`, `bchart.controlsExpanded`, `abpanel.a/b.controlsExpanded`, all default expanded).

- **Header**: chevron + "Date & Metrics" expander, and (only when at least one preset exists) the **preset menu button** showing the applied preset's name or "Presets ▾".
- **Preset menu** (tooltip "Filter presets"): alphabetical rows; clicking a row applies the preset (dates, include/exclude steps, meta filters, step/time/score ranges) and reloads; ✓ marks the applied one; each row has a **🗑** delete button (tooltip "Delete "\<name\>""). Presets are created in the sidebar (they capture the whole current filter state). Esc or clicking outside closes.
- **Journey time slider** (see §6).
- **Metric chips**: the five metrics (§4). One is active; disabled while no data. In A/B, changing a side's metric updates that side only (and the shared metric if that side is active). Chosen metric persists per chart via the saved chart state.
- **Date-slider mode toggle** (right end of the metric bar, ⇥ icon, tooltip "Date slider mode"): segmented **Range | Day**, persists as setting `slider.mode` (default **Range**).

## 6. Journey time slider

- Shows the current **from** date (and **to** date in Range mode) above the track, and the min/max bounds of the project's data range below it.
- **Range mode**: two thumbs (aria labels "Window start" / "Window end"). Thumbs cannot cross. Dragging previews only; **the query fires on release** (never per pixel). Clicking the track grabs the nearer thumb.
- **Day mode**: one thumb (aria "Day"); commits a single day on release. If no journeys exist on that day, the app searches for the nearest date with data: on success it snaps the slider and alerts — title "**No Journeys on \<date\>**", message "No journeys were found on \<date\>. Jumped to the nearest date with data: \<nearest\>."; if none exist anywhere nearby — title "**No Journey Data**", message "No journeys exist for this date or any nearby dates."
- Keyboard: Arrow keys ±1 day, Home = range start, End = range end (each commits).
- Degenerate range (0 days or unparsable bounds): the slider is replaced by two native date inputs "from – to" that commit on change.
- The slider stays in sync with the store when a preset is applied or a project loads. Initial window: last **30** days of data (setting `graph.defaultWindowDays`, 0 = full range).

---

## 7. A-Chart / B-Chart views

- A-Chart is the primary analysis chart; B-Chart is a second, independent chart with its own filters (both full-featured). Each remembers its own filter state and node layout.
- **Empty/error states**:
  - No project: 🗺 "**No Project Selected**" — "Select a project from the sidebar."
  - Load error: ⚠️ "**Failed to Load**" — the backend error message.
  - Loading (no data yet): spinner + "Loading process map" (A) / "Loading B-Chart" (B).
  - No data: 📊 "**No Process Data**" — A: "No event transitions found for this project."; B: "Use the sidebar filters and tap Apply to load the B-Chart." Both have a prominent **Load** button.
- **Footer** (data present): right-aligned "Query time: N ms" (or "N.NN s"), tooltip "Server-side execution time of the queries behind this view".
- If the chart's data source is a **simulation** (chosen in the sidebar Sampling section), the canvas shows the red read-only notice and node filter actions are hidden.

## 8. A/B Comparison

- Two side-by-side panels (A left, B right), each with: a **panel header**, optional KPI strip, its own Date & Metrics card, and a flow chart.
- **Panel header**: a button "✎ A-Chart · editing" (active side) or "○ B-Chart" — clicking makes that side *active* (sidebar filters then edit that side). Also: journey count ("N journeys"), a chevron toggling that panel's KPI strip (`abpanel.a/b.kpiExpanded`, default on). Panel A additionally has **⧉** "Copy A's node layout to B" (copies both viewport and node positions).
- **Valve button ⇄** between the panels: **open** = pan, zoom and node drags are synchronised across both panels (tooltip "Valve open — pan, zoom and reset are synchronised"); **closed** = independent (tooltip "Valve closed — charts move independently"). Closing snapshots A's current viewport/positions into B. Persists as `abComparison.valveOpen` (default **open**).
- Empty panel state: 📈 "**A-Chart**"/"**B-Chart**" — active side: "Apply filters in the sidebar to load."; inactive: "Tap the header to make this side active, then load." Both with a **Load** button (which activates the side and loads). Loading: spinner "Loading A-Chart/B-Chart".
- **Similarity badge** (bottom row, only when both sides computed): "⇄ Similarity N.NN", green ≥ 0.7 / red ≤ 0.3 / blue in between. Computed from both sides' journey-path variants + graphs.
- Each side's data source can be a **sample set** (Original / Sample 1–3) or a **simulation slot** (Sim-A / Sim-B) — chosen in the sidebar Sampling section; simulation sides are read-only (red notice, no Require/Exclude).
- KPI strips in A/B mode colour **Process Goodness** by comparison with the other side (green better / red worse / blue equal) and the **Active Sample** tile reflects the side's actual source (sample name or Sim-slot with its journey count).

## 9. Individual Journey

- Operated from the sidebar: enter an **Event ID** (autocomplete suggestions after 2+ characters) and tap **Load Journey**. The sidebar Metrics selector is hidden in this mode.
- The chart draws that single journey's steps in order; each node shows its event **time** (HH:MM:SS); edge metric is forced to **Avg Time** (count is meaningless for a single traversal); a blue dot animates along the edges in chronological order (§4).
- KPI strip: the Journey variant (§2).
- **States**:
  - Loading: spinner + "Loading journey".
  - Error: ⚠️ "**Failed to Load**" + message.
  - No project: 🗺 "**No Project Selected**" — "Select a project from the sidebar to view a journey."
  - No Event ID entered: 🧍 "**No Journey Selected**" — "Enter an Event ID in the sidebar and tap Load Journey."
  - Not found: 🔍 "**Journey Not Found**" — "No steps found for "\<entered id\>". Queried hash: \<hash\>".
- Node layout persists per event ID (chartMode key `ij_<eventId>`).

## 10. Conformance Check (power/admin only)

Compare actual transition values against per-edge target values ("norms"). Norms are stored **per project and per metric** (browser-independent backend storage).

- **Top KPI handle**: chevron collapses/expands the standard KPI strip (`compliance.kpiExpanded`, default on); collapsed it summarises "N violations · M compliant".
- **Toolbar row**: the five metric chips (select which metric's norms to view/edit — persists per project); checkbox **"Norm is a minimum"** (setting `compliance.normIsMinimum`, default **off**): off = actual must be ≤ norm to comply (norm is a cap); on = actual must be ≥ norm; **Show gaps / Hide gaps** button (tooltip "Toggle the gap-analysis table"); **Edit norms / Done** button (highlighted while editing).
- **Status line**: "❌ N violation(s)  ✅ M compliant  — K without norm", plus in edit mode the hint "Click an edge to set its norm".
- **View mode** (Edit off): edges colored by compliance (green/red/grey per §4), badge = actual value.
- **Edit mode**: edges uniform grey, badge = stored norm. Clicking an edge opens the **norm editor popover**: header "\<from\> → \<to\>", line "Actual: \<value\>" (Count adds " of outgoing"), a numeric input (placeholder **"Target %"** for Count, **"Target value (seconds)"** for time metrics; Enter saves), buttons **Clear** (deletes the norm) and **Set**. Empty or non-numeric input on Set also clears the norm.
  - **Count-norm budget helper** (Count metric only): norms are shares of the source node's outgoing flow and should total 100 %. The popover shows "X% on N other edge(s) from "\<step\>"", "**Y% remaining** to reach 100%", and if exceeded a red "Total would be Z% — over 100%" with a red border.
- **Gap table** (Show gaps): right-hand 460 px table with sortable-by-severity rows (violations first, then by delta descending): columns **From, To, Actual, Norm, Delta, Status** ("❌ Violation" red, "✅ Compliant" green, "— No norm" grey). Self-loop edges are excluded. Values format per metric (Count = %, time = duration, else integer).
- **States**: no project → 🗺 "No Project Selected"; no data → 🛡️ "**No Process Data**" — "Apply filters in the sidebar to load the process map." with **Load**.
- Node layout persists under chart mode "Conformance".

## 11. Happy Path (power/admin only)

Define an ideal step sequence ("happy path") and measure how closely real journeys follow it. Left: the actual process map (full flow chart, chartMode "HappyPath", same node/notes interactions as A-Chart). Right: the ideal-path pane (drag its left edge to resize, 300–1000 px; double-click the handle resets width to 460; persists as `happyPath.editorWidth`).

- **Top bar**: 🪧 icon; **path selector** dropdown (shows "No happy paths yet" when empty); **＋ New** (prompt sheet "New Happy Path" / "Give the ideal step sequence a name." — creating also switches into edit mode); when a path is selected: **✎ Rename** (prompt "Rename Happy Path", confirm "Rename") and **🗑 Delete**; a **Conformance score badge** when computed — "🪧 Conformance N.NN", green ≥ 0.7 / red ≤ 0.3 / orange between, tooltip "Journey-count-weighted edge coverage"; far right **✎ Edit Path** / **✓ Done** toggle.
- Left pane header: "Actual Process" + "N journeys". Empty state: 📊 "**No Process Data**" — "Apply filters in the sidebar to load the process map." + **Load**.
- Right pane header: the path name (or "Happy Path"), plus in edit mode a **＋ Add step…** dropdown listing steps not yet used anywhere in the path.
- **No path selected**: helper text "Define an ideal step sequence to measure how closely real journeys follow your intended design. Create one with "＋ New"."
- **Path selected but empty**: 🪧 "**No Steps Defined**" — edit mode: "Use ＋ to add the first step."; view mode: "Enable Edit Path to define the happy path."
- **View mode visualisation**: a vertical trunk of step cards connected by ⌄ chevrons. Each card is green-tinted when the step exists in the currently filtered process (tooltip = step name) and grey when not (tooltip "\<name\> — not present in the filtered process"). Cards for in-graph steps show a green **coverage percentage** = min(1, max(incoming, outgoing) ÷ filtered journeys). A **split** renders a "⑂ \<label or 'Split'\>" fork line, side-by-side branch columns headed "Branch 1", "Branch 2", … (empty branch shows "No steps"), and — when steps follow the split — a "⑃ \<rejoinLabel or 'rejoin'\>" line before the shared continuation. Splits nest (a split can live inside a branch).
- **Edit mode**: each step row has ▲ Move up / ▼ Move down / red ⊖ Remove step. Below the list: **＋ Add step…** and **⑂ Split** (tooltip "Add a split — alternatives that rejoin and continue"). A split card shows: ⑂ + label, ✎ Rename split (prompt "Rename Split"), ▲/▼ move, 🗑 Delete split; its branches (each an embedded editor; branches beyond 2 get a 🗑 Delete branch); **＋ Branch**; and, when steps follow the split, **✎ Rejoin: \<name\>** (prompt "Name Rejoin", confirm "Save"). Helper text: "Add a ⑂ Split for alternatives that rejoin — steps after a split are the shared continuation, and a split can be added inside a branch. Each journey is scored against the route it matches best." Button **↻ Recompute conformance** re-runs scoring.
- Conformance recomputes automatically on project/path change; edit mode is exited automatically when switching projects/paths. A step can appear only once across the whole path (used steps disappear from the add menus).

## 12. Simulation (power/admin only)

Monte-Carlo simulation built from the observed A-Chart graph (Markov model). Left 340 px configuration column, right results area.

- **Configuration** ("🎲 Simulation configuration"):
  - **Target slot** — segmented Sim-A | Sim-B (default Sim-A). Results are stored per slot so A/B can compare them.
  - **Journey count** — number, min 1, default **200**.
  - **Start date** — date input, default today.
  - **Average inter-arrival (hours)** — number, min 0.1, step 0.1, default **2**.
  - **Max steps per journey** — number, min 2, default **60**.
  - **Excluded steps** (collapsible picker; hint "Removed before the Markov model is built.") — multi-select list of all steps (◉ selected / ○ not); a count pill and an ⊗ clear button appear when any are selected.
  - **Required steps** (hint "Journeys not visiting all of these are discarded.") — same picker UI.
  - Warning when the A-Chart has no data: orange "Load the A-Chart first — simulation needs an observed process graph." (the store's own guard message is "Load the A-Chart first — simulation needs a process graph."). Any backend error appears in red above the button.
  - **Run simulation** button (spinner while running; disabled while running or without an A-Chart graph).
- **No results yet** state: 🎲 "**Sim-A — no results yet**" (or Sim-B) — "Configure the parameters and run the simulation. Results can then be selected as an A/B data source in the Sampling section."
- **Results header KPI tiles**: **Journeys** 👥, **Avg cycle time** ⏱️, **Shortest** 🐇, **Longest** 🐢, **Std dev** 〰️, **Variants** ⑂.
- **Results tabs** (segmented): **Flow | Variants | Charts | Event log**, plus **⤓ Export CSV** (downloads `Sim-A-event-log.csv` / `Sim-B-event-log.csv` with columns journeyId, step, timestamp — the FULL log).
  - **Flow**: the simulated process graph in the standard flow chart (uses the current transition metric; layout persists per slot).
  - **Variants**: table Path | Count | Share (%) | Avg cycle time.
  - **Charts**: "Cycle-time distribution" (12-bucket histogram) and "Top variants" (first 12 variants, bars labelled V1…V12; tooltip shows the full path).
  - **Event log**: note "Showing the first 1 000 of N events. Use "Export CSV" for the full log." and a Journey | Step | Timestamp table.
- Re-running a slot that is currently displayed as an A/B data source refreshes that A/B side automatically.
- No project: 🗺 "No Project Selected" — "Select a project from the sidebar."

## 13. AI supported Documentation

LLM-generated process documentation. Always analyses the **A-Chart** dataset/filters. Requires a connection profile with an LLM configured and reachable.

- **Pre-run screen**: large 🧠 glyph and three notice cards:
  - "**⛃ A-Chart filters in use**" — one-line summary: "\<from\> – \<to\> · N journeys · include: … · exclude: … · \<meta values\>".
  - "**🪧 Happy Path Conformance**" — warning-orange when none defined: "No Happy Paths defined — conformance data will not be included. Create one in the Happy Path view to enrich the analysis."; else "N path(s) will be evaluated: \<names\>".
  - "**🛡️ Conformance Check**" — warning when no norms: "No norms defined — gap analysis will not be included. Open Conformance Check and click edges in Edit mode to define target values."; else "N norm(s) across M metric(s) — gap analysis will be appended to the report."
  - **🧠 AI supported Documentation** run button — disabled when the LLM is unreachable, with orange note "⚠ LLM server not reachable. Check your connection profile."
- **Running**: spinner + "AI is analyzing" + the filter summary.
- **Failure**: ⚠️ "**Analysis Failed**" + error message + **↻ Try Again** (disabled if LLM unreachable).
- **Report screen**: toolbar with the filter summary, **Show prompt** (sheet "Prompt sent to the LLM" showing the exact prompt), **⎙ Print / PDF** (prints just the report via the browser print dialog), **↻ Re-run** (disabled if LLM unreachable). The report renders as Markdown with numbered chapters:
  1. project title + "_AI-Supported Process Documentation_" + quoted filter summary + "Generated: \<date time\>"
  2. **1. AI Analysis** (the LLM result)
  3. optional **Journey Paths**, **Happy Path Conformance**, **Conformance Check – Gap Analysis** chapters (numbered dynamically)
  4. **User Comments** — table Element | Type | User | Note | Date of all project notes (chronological)
  5. **Analysis Parameters** — model id and the prompt template (block-quoted).
- The prompt template is editable per project from the sidebar (persisted per project).
- No project: 🗺 "No Project Selected".

## 14. Notes (view, editor, list)

### Creating/opening notes from any chart
Click a node or edge → "✎ Show Notes (N)". With zero existing notes the editor opens directly to create one; with one or more, a **list sheet** opens ("Notes — \<target\>") showing every note as a card plus **＋ New note** and **Close** — so one node/edge can carry multiple notes.

### Note editor sheet ("New Note" / "Note", 🗒)
- Header: target (⬭ node name or ↝ "from → to"), plus importance badge and "✓ Resolved" when applicable.
- New note: **Title (optional)…** input + **Your note…** textarea. Existing note: read-only "Notes & comments so far" history box, then "Add a comment" with **Comment title (optional)…** + **Add a note or comment…** (comments append to the thread; a comment's title becomes the shown note title).
- **Mark this note / issue as resolved** checkbox (existing notes only) — anyone who can see the note may toggle it.
- **Importance** buttons: • Normal (default, muted), ℹ Info (blue), ★ Important (orange), ⚠ Urgent (red). Label reads "Importance (set by the author)" and buttons are disabled for non-authors.
- **Share with other users of this database** checkbox — author only.
- Footer: **Delete** (author only, existing notes; confirm sheet "Delete this note?" / "This removes the note and its whole comment thread from the database for everyone who can see it.") · **Cancel/Close** · **Save** (disabled until something changed; for a new note the text must be non-empty).
- Meta block: "Filter context: \<snapshot summary\>" (the filters active when the note was created: date window, include/exclude, meta values), "Created \<date\> by \<name\>", "Last activity \<date\> by \<name\>".
- **Permissions**: anyone may comment and resolve; only the author may change importance/sharing or delete. Failed sync shows alert "**Note Not Synced**" — "Note could not be written to the database: \<error\>" (or "…could not be updated: …").

### Notes view (list of all project notes)
- Empty state: 🗒 "**No Notes**" — "Click a node or an edge on the process map and choose "Show Notes" to add one."
- **KPI strip**: Total Notes 🗒, then one colored tile per importance (Normal •, Info ℹ, Important ★, Urgent ⚠ — counts respect all filters except the importance filter itself), then **Resolved** ✓ (green).
- **Row 1**: 🔍 search input (placeholder "Filter notes"; matches text, title and target; ⊗ clears), count "N of M", **↻ Reload**.
- **Row 2 filters** (all default "All"): **Type** (All / Node / Edge), **Importance** (All / Normal / Info / Important / Urgent), **Status** (All / Unresolved / Resolved), **User** (All / distinct authors by real name), **Time** (Any time / Last 7 days / Last 30 days / Last 90 days), **Sort** (Newest first — default / Oldest first), **Group by importance** checkbox (default **on** — groups Urgent→Normal with colored group headers "⚠ Urgent (N)" etc.), **Per page** (5 — default / 10 / 20).
- Note cards show: target icon + name, importance badge, "✓ Resolved" pill, 👥 shared icon (tooltip "Shared with other users"), author, created date, title (— if none), text, and the filter-context line. Clicking a card opens the editor.
- "No notes match the current filters." when filters exclude everything.
- **Pagination footer**: ‹ Prev · "Page X of Y" · Next › · "first–last of N". Any filter/sort change resets to page 1.

## 15. Statistics

Routes and analytics computed with **the same filters as Chart A** (info line "ⓘ Statistics use the same filters as Chart A."). Auto-loads once per project.

- **States**: loading → spinner "Computing journey routes"; no project → 🗺 "No Project Selected"; no data → ⑂ "**No Routes Yet**" — "Compute all journey routes for the current filters." + **↻ Compute Routes**; query error → ⚠️ "**Query Failed**" + message + **↻ Retry** (an alert "Statistics Error" with Retry/Cancel also appears).
- **KPI handle** + strip as in §2 (`statistics.kpiExpanded`, default expanded).
- **Stale banner** when any sidebar filter changed after the last computation: orange "⚠ Filters changed since last load" + **↻ Reload**.
- **Tabs** (segmented): **Routes | Analytics**.
- **Routes tab**:
  - 🔍 "Filter paths" search; count "N route(s)" with "(truncated)" appended when the server limited the result; **↻ Reload**.
  - **"Journeys over time"** line chart with granularity label Daily / Weekly / Monthly (server-chosen).
  - Sortable table (click headers; arrow ▲/▼ shows direction): **Journey Path | Journeys | Steps | Score/J | Total** (Total = score × journeys). Default sort: Journeys descending.
  - Pagination: ⇤ first, ‹ prev, "Page X of Y", › next, ⇥ last; **Rows** selector 25 (default) / 50 / 100 / 250.
- **Analytics tab**:
  - **"Journey duration distribution"** histogram ("No duration data." when empty).
  - **"Step traffic"** — horizontal bars, "Top 25 by visits" (visits = max(incoming, outgoing)); top step highlighted.
  - **"Transition heat map"** — matrix "rows = from · columns = to", blue intensity ∝ occurrences, cell tooltip "\<from\> → \<to\>: N" ("No transitions." when empty).
  - **"Duration KPIs"** — Shortest / Average / Std deviation / Longest.

## 16. Markdown rendering (AI report, help docs)

Supported: headings #–######, bold/italic/inline code, links (http/https/mailto/relative only — all other schemes neutralised), fenced code blocks, bullet & ordered lists, blockquotes, horizontal rules, pipe tables, and sanitized raw `<table>/<div>/<hr>/<h*>` blocks (DOMPurify — scripts/event handlers stripped). No images, no nested lists.

## 17. Gotchas & warnings worth a call-out box

- **Slider commits on release only** — dragging does not query; releasing does. In Day mode a day without data triggers an automatic jump to the nearest populated date (with an explanatory alert).
- **Statistics ≠ its own filters** — it always mirrors the A-Chart's filters; the stale banner appears if filters drift after computing.
- **Collapsed groups change edge numbers** — counts are summed, times weighted-averaged, intra-group transitions vanish; Min/Max/StdDev are unavailable on merged edges.
- **Count norms are percentages** of the source node's outgoing flow; keep each node's outgoing norms ≤ 100 % (the editor shows the remaining budget and warns in red when over).
- **Simulation data is read-only** everywhere it appears (red canvas notice; Require/Exclude hidden).
- **Node layouts, collapsed-group states, presets, happy paths, norms and the LLM prompt are stored server-side per user** (they survive browser changes and round-trip through backups); layouts are additionally keyed per project **and** per chart mode, so the A-Chart and B-Chart can be arranged differently. "↺ Reset node layout" clears manual positions for the current chart only.
- **Roles**: Conformance Check, Happy Path and Simulation are hidden from plain users (power + admin only). Note importance/sharing/deletion are author-only; commenting and resolving are open to all viewers.
- **Preset deletion is immediate** (🗑 in the preset menu, no confirm). Happy-path deletion is immediate too; note deletion requires confirmation.
- The AI Documentation "Re-run"/run buttons stay disabled until the connection's **LLM server is reachable**; the report always uses the **A-Chart** dataset regardless of the active view when triggered.
- The Individual Journey mode hides the sidebar Metrics selector and always shows **Avg Time** on edges; "Journey Not Found" echoes the queried hash for support/debugging.
- Double-clicking the chart background fits the view; double-clicking the Happy Path resize handle resets the pane width.