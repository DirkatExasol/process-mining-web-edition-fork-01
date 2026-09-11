# Documentation Notes — Main-App Sidebar, Connection Editor, Sampling, Configuration, Notes Filters

Source: `frontend/web/src/components/Sidebar.tsx`, `ConnectionEditor.tsx`, `SamplingSection.tsx`, `StepEditor.tsx`, `AuthFooter.tsx`, `ThemeBar.tsx`, `ui.tsx`, `store.ts`, `settings.ts`, `types.ts`, `views/NotesView.tsx`, `backend/app/api/connections.py`.

---

## 1. Sidebar — general behaviour

- The sidebar is the left panel of the main app. Top-to-bottom: **brand header** ("Process Mining" over the caption "Demonstrator", with logo) → divider → accordion sections → **signed-in identity footer** → divider → **theme bar**.
- Accordion sections, in order: **Connections**, **Projects**, **Metrics**, **Filters**, **Sampling**, **Configuration**. Opening one section collapses all others (only one open at a time). On app start, **Connections** is open.
- **Connections** and **Projects** headers show a count in parentheses, e.g. "Connections (3)" — only shown when the count is > 0.
- Section headers toggle open/closed via a chevron + title button.
- Special mode behaviour:
  - Switching the main view to **Individual Journey** automatically opens the **Filters** section (so the Event ID field is immediately available). This fires once per mode change; the user can collapse it again afterwards.
  - In **Individual Journey** mode the **Metrics** and **Sampling** sections are hidden entirely (Individual Journey always renders with a fixed Avg Time metric).
- **Hide/show sidebar**: the theme bar at the very bottom has a "Hide sidebar" button (⇤). When hidden, a "Show sidebar" button (▤) appears in the chart header of the detail pane.
- **Theme bar**: "🎨 Theme" with three icon buttons — **System** (◐), **Light** (☀), **Dark** (☾). Persists per user as setting `app.theme` (default `system`).

### Signed-in identity footer (AuthFooter)
- Row 1: 👤 + display name (or username), then the role in parentheses. Role label precedence: **Admin** > **Power user** > **Developer** > **User** (a user who is both power and developer shows "Power user"). Hovering shows "Display Name (username)".
- Row 2 buttons (each shown only when the server allows the feature for this user):
  - **🔒 Two-factor** (tooltip "Manage two-factor authentication") — opens the two-factor sheet.
  - **🔑 Passkeys** (tooltip "Manage passkeys for this account") — opens the passkeys sheet.
  - **⏻ Sign out** (always shown) — signs the user out of the app.
- The footer is hidden entirely when no user is signed in (login not required deployments).

---

## 2. Connections section

### Header controls
- **＋** button, tooltip **"New connection"** — visible only to *connection managers* (users with the **power**, **admin**, or **developer** role). Opens the Connection Editor in "New Connection" mode (and refreshes the manageable-connections list first).
- **↻** button, tooltip **"Refresh connections"** — visible to everyone; re-fetches the assigned-connection list and current connection status.

### Connection list
- Cards are sorted **alphabetically by name**. List scrolls (max height ~300 px).
- Each card shows:
  - A database glyph (⛁) — **green** when this card is the connected one, accent-coloured otherwise.
  - **Name** (falls back to "(unnamed)").
  - Optional **comment** line.
  - "**Database:** host:port" (host falls back to "(no host)").
  - If the connection has an LLM configured: "**LLM:** \<URL\>" (falls back to "(configured)").
- **Click a card** to connect. Clicking the *currently connected* card **disconnects**. Clicking a different card while connected disconnects first, then connects to the new one. On successful connect, the sidebar automatically opens the **Projects** section and loads the project list.
- **Status dots** (right side, only on the *active* card):
  - Database dot: **green** = "Connected", **orange** = "Not connected" (tooltips as quoted).
  - LLM dot (only when the connection has an LLM configured): **blue** = "LLM reachable", **orange** = "LLM not reachable".
- **✎ Edit** button (tooltip "Edit connection"): shown only to managers, and only on connections that appear in their manageable list (a power user/developer sees the pencil only on connections they own; an admin sees it on all). Clicking it opens the Connection Editor without connecting.
- **Empty states**:
  - Manager: *"No connections yet. Use ＋ above to create one and assign users."*
  - Plain user: *"No connections assigned to you. Ask an administrator to grant access."*
- **Errors**: the last connection error is shown in red beneath the list (or in the empty state). A failed connect additionally raises an alert titled **"Connection Failed"** with the error message and buttons **Retry** / **Cancel** (Retry re-attempts the same connection). Unexpected API failures raise "Connection Failed" with a single **OK** button.
- Backend refusals a user can see: *"This connection is not available to you."* (403), *"Connection not found."* (404).
- **Disconnecting** clears the whole session state (project, filters, graphs) but does **not** sign the user out of the app.

### Who sees what
| Capability | Plain user | Power | Developer | Admin |
|---|---|---|---|---|
| See/connect assigned connections | ✔ | ✔ | ✔ | ✔ |
| ＋ New connection / ✎ Edit | — | ✔ (own only) | ✔ (own only) | ✔ (all) |
| Sampling section | — | ✔ | — | ✔ |

Backend enforcement mirrors this ("You are not allowed to manage connections." on 403). Ownership is enforced per connection: power users/developers manage only connections they created; admins manage all.

---

## 3. Projects section

- Header **↻** button, tooltip **"Reload projects"** — disabled unless a database is connected.
- States:
  - Not connected: *"Connect to a database to load projects."*
  - Loading (first load): spinner + "Loading".
  - Empty: *"No projects found."*
  - Failure: alert **"Failed to Load Projects"** with **Retry** / **Cancel**.
- Each project card: 📈 icon, **title**, optional description; the selected project shows a ✓. List scrolls (max ~240 px).
- **Selecting a project** collapses all sidebar sections and:
  - Switches the view to A-Chart and resets all filters, A/B state, statistics, and AI results.
  - Loads project bootstrap data (steps, meta titles/values, date range, filter bounds, sample counts).
  - Applies the **Default date window** setting: from-date = latest event date minus N days (default N = 30), clamped to the project's earliest date; N = 0 shows the full range.
  - Loads per-user, per-project persisted state: filter presets, target norms, happy paths, and the LLM prompt template.
  - Failure raises **"Failed to Load Project"** with **Retry** / **Cancel**.

---

## 4. Metrics section

- Hidden in Individual Journey mode.
- Label: "ƒ Transition metric". A 2-column grid of chips, disabled until a project is selected:
  - **# Count** (default), **⏱ Avg Time**, **⌄ Min Time**, **⌃ Max Time**, **〰 Std Dev**.
- In A/B Comparison mode, changing the metric applies it to the currently edited side (A or B).

---

## 5. Filters section

### Mode-specific replacements
- **Individual Journey**: the section shows only the **Event ID** filter (see 5.4).
- **AI supported Documentation**: shows only the notice *"AI supported Documentation uses the filter conditions from the A-Chart."* (ⓘ icon) — no editable filters.
- **A/B Comparison**: an extra row at the top, "Editing:" with a segmented control **A-Chart | B-Chart**, switches which side's filters the sidebar edits.
- **Statistics**: filters look normal, but **Apply** reloads the statistics view instead of the graph. (Statistics always inherits Chart A's filter state on entry.)

### 5.1 Filter sub-sections
Each sub-section has a collapsible header; expansion state persists per user. Defaults: **Date expanded**, all others collapsed. Active sub-sections show a **badge** with the current value and a **⊗ clear** button (tooltip "Clear \<Title\>").

1. **Date** — "From" and "To" date pickers.
2. **Include Steps** — searchable step list. Badge = number of included steps. Search field placeholder "Search" with a ⊗ clear button (tooltip "Clear search"). Rows are radio-style (◉ selected / ○ not); steps already in *Exclude Steps* appear disabled here (and vice versa) — a step can never be both included and excluded. Empty states: *"No project selected"* (no steps loaded) and *"No matches"* (search found nothing).
3. **Exclude Steps** — identical UI, mirrored.
4. **Num Steps** — dual-handle range slider between the project's min/max step counts. Badge e.g. "2–14". Disabled when no project or when min equals max.
5. **Journey Time** — range slider with human-readable durations (e.g. "3m 20s"). Badge shows the formatted range. Disabled when no project or bounds are degenerate.
6. **Journey Score** — range slider over the project's score bounds. Only meaningful when steps have scores. Disabled when no project or bounds are degenerate.
7. **Meta** — appears **only** if the project defines at least one meta attribute title. Badge = number of meta filters currently set; ⊗ clears all three. Contains up to three **autocomplete combo fields**, labelled with the project's meta titles. Placeholder: **"All values"**. Focusing shows the full distinct-value list (max 50 entries shown, scrollable); typing filters it; a **▾** button (tooltip "Show values") opens/closes the list; a ⊗ button (tooltip "Clear") clears the value. Enter confirms; Escape closes the list.

Nodes on the process map can also be added to include/exclude filters via node context actions; adding to one list removes from the other, and the graph reloads immediately.

### 5.2 Action row
- **↺ Reset** — restores all filters to the project's initial values (initial date window, empty step lists, empty metas, full bounds) and immediately reapplies (reloads graph, or statistics in Statistics mode).
- **🔖 Save Preset…** — opens the **"Save Filter Preset"** sheet: message *"Saves the current filter settings as a named preset."*, a **Name** field, buttons **Cancel** / **Save**. Enter confirms. If the name is left empty, the preset is auto-named "Preset N".
- **Apply** (prominent) — reloads the graph (or statistics) with the current filters.
- All three are disabled until a project is selected.

### 5.3 Presets list
- Appears under the action row only when at least one preset exists; heading "Presets".
- Presets are listed **alphabetically (A→Z)**, matching the chart header's preset picker. At most four rows are visible; more scroll.
- Clicking a preset name **applies it and reloads the graph immediately** (dates, step lists, metas, all range bounds). The applied preset row is highlighted.
- Row buttons: **✎** (tooltip "Rename preset") → **"Rename Filter Preset"** sheet with the current name prefilled and a **Rename** confirm button; **🗑** (tooltip "Delete preset") → deletes immediately, **no confirmation dialog** (gotcha).
- Storage: presets are saved **per user and per project** in the backend settings store (they survive browser changes but are *not* shared with other users — unlike sample sets; see the Sampling info note).

### 5.4 Event ID filter (Individual Journey mode)
- Label "Event ID"; text input with placeholder **"Enter EVENT_ID"** (autocorrect/autocapitalise/spellcheck off).
- Typing ≥ 2 characters fetches **suggestions** (matching event IDs from the current project and active A sample set); a dropdown appears while the field is focused. Clicking a suggestion fills the field and loads the journey immediately. Fewer than 2 characters clears the suggestions.
- ⊗ button (tooltip "Clear") empties field and suggestions.
- **Enter** in the field loads the journey. The **"Load Journey"** button (prominent, right-aligned) does the same; it is disabled when the field is blank or no project is selected.
- Errors from loading are shown in the app's standard error area, not inside the sidebar.
- Note for demo data users: demo EVENT_IDs are MD5 hashes of "ORD-000001"/"CRA-000001"/"FLT-000001"-style keys (see §9.2), so suggestions are hex strings.

---

## 6. Sampling section

- **Visibility: power users and admins only** (not plain users, not developers), and hidden in Individual Journey mode.
- Info note at the top (ⓘ): *"Sample sets are stored in the project's database and are shared by everyone connected to it — unlike your personal settings and filter presets. Creating or deleting one changes it for all users of this project."* — worth surfacing as a warning in the manual.

### 6.1 Active data pickers
- Heading "▤ Active data". Two dropdowns, labelled **A** (accent blue) and **B** (purple), disabled until a project is selected. Each selects the data source that side's chart reads from:
  - **Original (N)** — full data, always selectable; N = total journey count.
  - **Sample 1/2/3 (N · Method)** — e.g. "Sample 1 (1,000 · Random)"; option is **disabled** with label "Sample 1 — not created" until that set exists.
  - **Sim-A / Sim-B (N sim)** — a simulation run's output; disabled with "Sim-A — not loaded" until a simulation has been run into that slot. Choosing a simulation source makes that side **read-only** (the canvas shows: "\<slot\>: simulation data is read-only — interactive filtering, drill-down and step editing are not available.").
- Selecting a sample set persists per user (settings `sampling.activeSampleSetA`/`B`, default `ORIGINAL`) and reloads the appropriate chart. If a persisted sample no longer exists when a project loads, the side silently falls back to Original.

### 6.2 Sample slots
- Three rows: **Sample 1**, **Sample 2**, **Sample 3**. Each shows:
  - ◉ (accent) when created / ◌ when not; the row title is bold+accent when that set is active on A or B.
  - Created: "N journeys" plus a method tag (icon + label, tooltip "Sampling strategy: \<Method\>").
  - Not created: the text "Not created".
- Buttons per row: **＋** (tooltip "Create Sample N") when not created — disabled while no project is selected or a sampling operation is running; **🗑** (tooltip "Delete Sample N") when created.
- While an operation runs, a spinner row shows the progress text ("Preparing…", "Writing N journeys…", or fallback "Working…"). Errors appear in red under the pickers.

### 6.3 Create Sample sheet
- Title: **"Create Sample Set N"** (icon ▤).
- Shows "N journeys available" (total in the original data).
- **Journeys** field — free-typed number, default **1000**. The Create button is disabled unless the value is a positive integer.
- **Sampling Method** — one of three selectable cards (the last used method is remembered per user as the default; initial default **Random**):
  - 🔀 **Random** — "Uniform random selection"
  - 📅 **Temporal Stratified** — "Proportional across time periods"
  - 🌿 **Path Diversity** — "Coverage across journey variants"
- Buttons: **Cancel** / **Create Sample** (with spinner while running). While creating, Cancel and closing the sheet are disabled. On success the sheet closes; on failure it stays open and shows "⚠ \<error\>".

### 6.4 Delete confirmation
- Title: **"Delete Sample Set N?"**. Message: *"This removes \<count\> sample journey rows from the database. Original data is not affected."* Buttons **Cancel** / **Delete** (red).
- Gotcha: if the deleted set was active on side A or B, that side automatically switches back to **Original** and the chart reloads.

---

## 7. Configuration section

Ordered top to bottom. The four collapsible sub-headers (Step Groups, Flowchart Font Sizes, KPIs, Steps) are all **expanded by default**; their expansion state persists per user.

### 7.1 🗂 Step Groups
- **"Show step groups"** toggle — default **on**. When on, an additional setting appears:
- "▦ Groups start" segmented control: **Expanded** (default) | **Collapsed** | **Persisted**. Controls whether group containers on the process map start open, closed, or remember their last state per project/chart.

### 7.2 🔠 Flowchart Font Sizes
Three segmented controls, each **S | M | L | XL**:
- **Nodes** — default **M**. (Internally S=1.95, M=2.25, L=2.7, XL=3.15 scale factors; enlarging the font also grows the node so text stays inside.)
- **Edges** — default **M**. Edge label presets run 50% larger than node presets (S=2.925 … XL=4.725) so transition labels read larger.
- **Group titles** — default **M** (same scale steps as Nodes).

### 7.3 📊 KPIs
- A drag-to-reorder list (≡ handle; drag a row onto another to reorder — order persists per user) of KPI toggles, each with an icon, label and on/off switch. **All default on.** Default order:
  1. 👥 Total Journeys
  2. ⛃ Filtered Journeys
  3. 🐇 Shortest Journey
  4. ⏱️ Avg Journey
  5. 〰️ Std Dev
  6. 🐢 Longest Journey
  7. ƒ Graph Value
  8. ◔ Process Goodness
  9. ⇄ Process Similarity
  10. ▤ Active Sample
- Order and visibility control the KPI strip above the charts.

### 7.4 ⬭ Steps (Step Editor)
- **Step** dropdown — "— Select a step —" plus every step of the project; disabled when no project/steps. The editor below only appears once a step is chosen.
- **Colors** — two colour pickers labelled **BG** and **FG**, with a live pill preview of the step in those colours.
- **Score** — a "set" checkbox plus a number input (−999…999), disabled unless the checkbox is ticked. Unticking saves the score as unset.
- **Shape** — chips: **▭ Stadium** (default), **▢ Rounded**, **⬡ Hexagon**, **◯ Circle**.
- **Group** — free text with autocomplete of existing group names; placeholder "BELONGS_TO". Assigns the step to a step group.
- **Note** — multi-line text; placeholder "Shown under the step name on the map".
- **Save Step** button (with spinner) writes to the database (changes are shared — they live in the STEPS table). Errors appear in red next to the button. Saving refreshes score filter bounds and reloads the graph.

### 7.5 Non-collapsible toggles
- 🗒 **"Show node notes"** — default **on**. Shows step descriptions/notes under node names on the map.
- ✨ **"Optimise layout"** — default **on**.
- 🎨 **"Colorise edges by weight"** — default **on**.

### 7.6 🗓 Default date window
- Row: "Default date window" + number input (min 0, integer) + "days". Default **30**.
- Hint text below: *"On load, show the last N days. 0 = full range. Applies next project load."*
- Gotcha: changing it does not reload the current project; it takes effect the next time a project is opened.

### 7.7 💬 LLM Prompt
- Row: "LLM Prompt" + **Edit** button — disabled until a project is selected.
- Opens the **"LLM Prompt Template"** sheet:
  - Explanation: *"This prompt is sent to the LLM together with the current transition table. Use it to guide the analysis style and output format."*
  - A large textarea with the current template.
  - Footer: **Reset to Default** (restores the built-in default into the editor, still needs Save), **Cancel**, **Save**.
  - Default prompt text: `Analyze the transitions table and identify outliers, min, max, avg values for transitions. Use project name as a title, make a decent layout.`
  - The template is stored **per user and per project**.

---

## 8. Connection Editor (managers only)

Opened from **＋ New connection** or **✎ Edit connection** in the Connections section. A wide modal sheet titled **"New Connection"** or **"Edit Connection"** (⛁ icon). Escape, the ✕ button, or clicking outside closes it **without saving**.

### Footer (always visible)
- **Test** — tests the *currently typed* values (see below).
- Test result text next to the button, colour-coded: **green** = everything OK; **orange** = one of two components failed; **red** = all tested components failed. Format: "Database OK" or "Database: \<error\>", joined with "  ·  " and, if an LLM URL is set, "LLM OK (N models)" or "LLM: \<error\>". (Model count omitted when zero. Backend LLM failure message: "LLM server not reachable.")
- **Delete** (red; edit mode only) → confirmation **"Delete connection?"**: *"“\<name\>” will be removed for all assigned users. This cannot be undone."*, buttons **Cancel** / **Delete**. On backend failure the sheet shows "Delete failed."
- **Cancel**, **Save** (prominent). Save validates that **Name** is non-empty ("Name is required." shown in red at the top otherwise); other save errors from the backend are shown the same way ("You cannot edit this connection." etc.).

### Tabs
**Database / LLM Details** · **Demo Content** · **Projects** (Projects only appears when editing an existing connection).

### 8.1 Database / LLM Details tab

Fields (label — behaviour/default):
- **Name** — required; the display name in everyone's Connections list.
- **Comment** — optional description line shown on the card.
- Section **Database**:
  - **Host** — default empty.
  - **Port** — number, default **8563** (Exasol default).
  - **Username** — database login.
  - **Schema** — database schema holding the process-mining tables.
  - **Password** — password field. **Write-only secret**: when a password is already stored, the placeholder reads **"•••••• (unchanged)"**; leaving the field untouched keeps the stored password; typing sends the new value; deliberately clearing to empty **erases** the stored password.
- **Create schema & tables** button (in a boxed panel; disabled while busy or when Schema is blank). Result to the right: green "Created: \<list\>" on success, red error otherwise (fallback "Could not create the schema."). Explanation text: *"Creates the “\<schema\>” schema and the process-mining tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don't exist. This needs a database account permitted to CREATE SCHEMA and CREATE TABLE — only your database administrator can grant those rights; the app cannot. Uses the credentials entered above."*
- **Use TLS** checkbox — default **off**. When on, three more fields appear:
  - **Certificate mode** dropdown: **"Verify (system trust store)"** (default), **"Pin fingerprint"**, **"Accept any (insecure)"**.
  - **Fingerprint (SHA-256)** — placeholder "optional"; used with the pin mode.
  - **Minimum RSA key size** — number, default **2048** bits.
- Section **LLM (optional)**:
  - **Server URL** — placeholder "https://…". Leave empty for no LLM; the app then hides LLM indicators for this connection.
  - **Model** — model name to use.
  - **API key** — password field with the same **write-only** semantics as Password (placeholder "•••••• (unchanged)" when one is stored).
- Section **Assigned users**:
  - A scrollable checkbox list of every enabled username; ticked users see and may use this connection. Empty state: "No users available."
  - When *creating* a connection, the creator is automatically the **owner** and is auto-assigned even if unticked.

**Gotchas / warnings:**
- **Test / Create schema & tables / demo generation all use the password typed into the sheet — not the stored secret.** When editing an existing connection you must re-enter the database password before Test/provision/demo will authenticate.
- **Saving an edit disconnects every user currently connected through this connection** (they must reconnect against the new definition). Un-assigning a user also takes effect immediately — their live session is dropped.
- Deleting a connection also drops all live sessions on it first.
- Backend permission errors the sheet can show verbatim: "You are not allowed to manage connections.", "You cannot edit this connection.", "You cannot delete this connection.", "You cannot manage this connection.", "You cannot re-assign this connection.", "Connection not found."

### 8.2 Demo Content tab

Intro text: *"Generate a ready-made dataset into this connection's schema — it creates the schema and the process-mining tables if needed, then loads the journeys (replacing only that dataset's own project). Needs a database account permitted to CREATE SCHEMA, CREATE TABLE and INSERT — only your database administrator can grant those; the app cannot. Uses the credentials on the Database / LLM Details tab."*

Three dataset panels, grouped under headings **Retail**, **Finance/Insurance**, **Transportation**:

1. 📚 **Online Bookstore** — *"Order lifecycle: login → browse → basket → checkout → payment → fulfilment → delivery, with a returns flow and a deliberately flaky bank-transfer path. Each EVENT_ID is the MD5 hash of “ORD-000001”, “ORD-000002”, … (the prefix ORD- plus a 6-digit sequence number)."*
2. 💶🪙 **Online Credit Application** — *"Bank/affiliate intake → application check (with a rework loop) → credit assessment → score- and sum-driven approval with agent-review loops, ending in payment or rejection. Each EVENT_ID is the MD5 hash of “CRA-000001”, …"*
3. ✈️ **Flight Booking & Management** — *"Star Alliance-style booking: login → search (with a modify loop) → select → book → payment (Credit Card, SEPA, Apple Pay, Google Pay, Advance Payment) → confirm. 50% of bookings are interline (multi-airline) and query a partner airline's system; 20% only manage an existing booking (seat reservation / ancillary services). Each EVENT_ID is the MD5 hash of “FLT-000001”, …"*

Each panel has:
- **Schema** field (placeholder "DEMO") — note: this is **the same schema value as the Details tab**; editing it in any demo panel changes the connection's schema draft.
- **Journeys** number field — default **500**, min 1, max 20,000 (typed, not stepped).
- **Generate** button (prominent; shows "Generating…" with spinner while running; disabled while busy, when Schema is blank, or journeys < 1).
- Result line: green success message (backend message, fallback "Created N journeys.") or red error (fallback "Could not generate demo content.").
- Generating replaces only that dataset's own demo project — other projects in the schema are untouched.

### 8.3 Projects tab (edit mode only)

- Description: *"Projects stored in the “\<schema\>” schema, with their journey and event counts. Deleting a project clears its rows from every table (PROJECTS, JOURNEYS, STEPS, METAS, NOTES, TRANSITIONS_RAW) — this cannot be undone."*
- **↻ Refresh** button. The list loads automatically the first time the tab is opened.
- States: "Loading projects…" with spinner; empty: *"No projects found in this schema."*; error (red): backend message or *"Could not read the projects for this connection."*
- Each row: project **title** (with the raw project ID underneath when it differs), "**N journeys**", "**N events**", and a red **Delete** button.
- Delete confirmation: **"Delete project?"** — *"“\<title\>” (\<journeys\> journeys, \<events\> events) will be cleared from PROJECTS, JOURNEYS, STEPS, METAS, NOTES and TRANSITIONS_RAW in this schema. This cannot be undone."* Buttons **Cancel** / **Delete project**. Failure shows the backend message or *"Could not delete the project."*
- Project deletions are recorded in the admin audit log (who deleted what from which connection).

---

## 9. Notes filters (Notes view)

The Notes view (main-pane mode "Notes", 🗒️) has its own filter bar; the sidebar's standard filters do not apply here.

- **Empty state** (no notes at all): 🗒 **"No Notes"** — *"Click a node or an edge on the process map and choose “Show Notes” to add one."*
- **KPI strip** across the top: **Total Notes** (🗒), then one tile per importance in ascending order — **Normal** (•, muted), **Info** (ℹ, blue), **Important** (★, orange), **Urgent** (⚠, red) — then **Resolved** (✓, green). Counts reflect all filters *except* the Importance dropdown, so the breakdown always shows the full context.
- **Row 1**: search field, placeholder **"Filter notes"** (matches note text, title and target label; ⊗ clears), a "\<shown\> of \<total\>" counter, and **↻ Reload**.
- **Row 2** — dropdowns and options (defaults in bold):
  - **Type**: **All** | Node | Edge.
  - **Importance**: **All** | Normal | Info | Important | Urgent.
  - **Status**: **All** | Unresolved | Resolved.
  - **User**: **All** | one entry per note author (labelled with real name where available, sorted alphabetically).
  - **Time**: **Any time** | Last 7 days | Last 30 days | Last 90 days (based on creation date).
  - **Sort**: **Newest first** | Oldest first.
  - **Group by importance** checkbox — **checked** by default; groups notes with the highest importance group first.
  - **Per page**: **5** | 10 | 20.
- Changing any filter, the sort, the grouping, or the page size resets to page 1.
- No matches: *"No notes match the current filters."*
- Note sync failures raise alerts titled **"Note Not Synced"** ("Note could not be written to the database: …" / "Note could not be updated: …") with **OK**.

---

## 10. Cross-cutting persistence model (worth a manual sidebar/box)

- **Per-user, cross-device (backend settings store)**: theme, all Configuration toggles/scales, KPI order/visibility, filter sub-section expansion, active sample-set choices, default sampling method, filter presets, LLM prompt templates, happy paths, target norms. These survive browser changes and are included in backups; they are private to the user.
- **Shared in the project database (all users)**: sample sets (SAMPLE_1–3), step properties edited in the Step Editor (colours, scores, shapes, groups, step notes), notes, projects, demo data.
- **Session-only**: current connection, selected project, unsaved filter edits, Notes-view filter settings (reset on reload).