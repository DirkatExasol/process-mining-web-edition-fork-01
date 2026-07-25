/**
 * In-app help content — ported from HelpView.swift.
 *
 * The block model mirrors the Swift `HelpBlock` enum so the same structured,
 * example-driven documentation renders here (paragraph / tip / warning /
 * bullets / definition / code). The Process Goodness, Process Similarity and
 * Simulation chapters are ported verbatim, including every worked example.
 */

export type HelpBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'tip'; text: string }
  | { kind: 'warning'; text: string }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'definition'; term: string; detail: string }
  | { kind: 'code'; text: string }

export interface HelpSection {
  heading: string
  body: HelpBlock[]
}

export interface HelpTopic {
  id: string
  title: string
  subtitle: string
  icon: string
  sections: HelpSection[]
}

// Block constructors — keep the content below terse and readable.
const p = (text: string): HelpBlock => ({ kind: 'paragraph', text })
const tip = (text: string): HelpBlock => ({ kind: 'tip', text })
const warn = (text: string): HelpBlock => ({ kind: 'warning', text })
const ul = (...items: string[]): HelpBlock => ({ kind: 'bullets', items })
const def = (term: string, detail: string): HelpBlock => ({ kind: 'definition', term, detail })
const code = (text: string): HelpBlock => ({ kind: 'code', text })

// ── Overview ──────────────────────────────────────────────────────────────────

const overview: HelpTopic = {
  id: 'overview',
  title: 'Overview',
  subtitle: 'What Process Mining Demonstrator does and key concepts',
  icon: '🏠',
  sections: [
    {
      heading: 'What is Process Mining Demonstrator?',
      body: [
        p('Process Mining Demonstrator is a process-mining tool that connects to an Exasol database and visualises how real cases flow through your business processes.'),
        p('It reads a JOURNEYS table and renders every possible path between process steps as an interactive flow chart, with rich filtering, side-by-side comparison, and individual journey inspection.'),
      ],
    },
    {
      heading: 'Workflow at a glance',
      body: [
        ul(
          'Sign in, then open the sidebar Connections section — it lists the database connections an administrator has assigned to you.',
          'Tap a connection to connect; the Projects section opens automatically.',
          'Select a project — the A-Chart loads for the last 30 days of data.',
          'Choose a chart view from the ☰ menu in the top-right corner of the main area.',
          'Adjust filters in the sidebar and tap Apply to refresh the map.',
          'Each chart view remembers its own filter settings independently.',
        ),
      ],
    },
    {
      heading: 'Data model',
      body: [
        def('Journey / Case', 'One end-to-end instance of a process, identified by EVENT_ID.'),
        def('Step / Event', 'A single activity within a journey, stored as a row in JOURNEYS.'),
        def('Transition', 'A chronologically consecutive pair of steps within the same journey.'),
        def('Meta attributes', 'Up to three free-text columns (META_1 – META_3) carrying case-level attributes such as department or customer segment.'),
      ],
    },
    {
      heading: 'The ten views',
      body: [
        p('Open the ☰ menu (top-right) to switch between: A-Chart, B-Chart, A/B Comparison, Individual Journey, AI supported Documentation, Statistics, Conformance Check, Happy Path, Notes and Simulation. A checkmark marks the active view, and the title capsule shows it on a second line so you always know your context.'),
        tip('Press ⌘/ (or Ctrl+/) at any time to open or close this Help panel. It floats, and can be dragged by its title bar and resized from the bottom-right corner.'),
      ],
    },
  ],
}

// ── Database setup ────────────────────────────────────────────────────────────

const database: HelpTopic = {
  id: 'database',
  title: 'Database Setup',
  subtitle: 'Table schemas and required permissions',
  icon: '🗄',
  sections: [
    {
      heading: 'Required tables',
      body: [
        p('Process Mining Demonstrator reads from four tables — PROJECTS, JOURNEYS, STEPS and METAS. A NOTES table and the JOURNEYS.SAMPLE_SET column are created automatically on first use if the connecting user has the necessary rights. All table and column names are case-insensitive in Exasol.'),
        code(
          `CREATE TABLE PROJECTS (
  PROJECT_ID  VARCHAR(100) NOT NULL PRIMARY KEY,
  TITLE       VARCHAR(200) NOT NULL,
  DESCRIPTION VARCHAR(500)
);

CREATE TABLE JOURNEYS (
  PROJECT_ID  VARCHAR(100) NOT NULL,
  EVENT_ID    VARCHAR(200) NOT NULL,   -- one journey = rows sharing an EVENT_ID
  STEP        VARCHAR(200) NOT NULL,   -- activity name → a node in the map
  STEP_ID     DECIMAL(18,0),           -- tie-breaker when EVENT_TIME is equal
  EVENT_TIME  TIMESTAMP    NOT NULL,   -- orders steps; drives date filters
  META_1      VARCHAR(500),
  META_2      VARCHAR(500),
  META_3      VARCHAR(500)
);

CREATE TABLE STEPS (
  PROJECT_ID     VARCHAR(100) NOT NULL,
  STEP           VARCHAR(200) NOT NULL,
  DESCRIPTION    VARCHAR(500),
  BG_COLOR       VARCHAR(50),          -- colour name or 6-digit hex (e.g. FF8000)
  FG_COLOR       VARCHAR(50),
  SCORE          DECIMAL(5,0),         -- −999…999, shown as a badge
  SHAPE          VARCHAR(20),          -- stadium | round | hex | circle
  END_OF_PROCESS DECIMAL(1,0) DEFAULT 0,
  BELONGS_TO     VARCHAR(200),         -- optional grouping label
  PRIMARY KEY (PROJECT_ID, STEP)
);

CREATE TABLE METAS (
  PROJECT_ID   VARCHAR(100) NOT NULL PRIMARY KEY,
  META_1_TITLE VARCHAR(200),
  META_2_TITLE VARCHAR(200),
  META_3_TITLE VARCHAR(200)
);`,
        ),
      ],
    },
    {
      heading: 'Permissions & performance',
      body: [
        ul(
          'SELECT on PROJECTS, JOURNEYS, STEPS, METAS — required for all read features.',
          'CREATE TABLE — needed once so the NOTES table can be auto-created (Notes feature only).',
          'ALTER TABLE + INSERT on JOURNEYS — needed for the Sampling feature (adds the SAMPLE_SET column and writes sample rows).',
          'UPDATE on STEPS — needed for the in-app Step Editor.',
        ),
        tip('For best performance, index JOURNEYS (PROJECT_ID, EVENT_TIME) and JOURNEYS (PROJECT_ID, EVENT_ID).'),
        p('No Exasol instance yet? The free Community Edition and the official Docker image both work. When using the Docker image or Exasol 7.x, set the connection’s minimum RSA key size to 1024 bits (legacy).'),
      ],
    },
  ],
}

// ── Connections ───────────────────────────────────────────────────────────────

const connecting: HelpTopic = {
  id: 'connecting',
  title: 'Connections',
  subtitle: 'Sign in, then pick a database connection assigned to you',
  icon: '⛁',
  sections: [
    {
      heading: 'Signing in',
      body: [
        p('Unless an administrator has turned sign-in off, the application asks you to sign in. Use the username and password you were given — depending on how your organisation is set up this may be a local account or a directory (LDAP / Active Directory) account.'),
        tip('Your app sign-in is completely separate from any database credentials. You never type a database password into the app — those live only in the administrator’s configuration.'),
      ],
    },
    {
      heading: 'How connections work',
      body: [
        p('A connection bundles one Exasol database server with an optional OpenAI-compatible LLM server. Connections are defined by an administrator in the admin interface and assigned to individual users.'),
        p('The Connections section of the sidebar lists only the connections assigned to you, as read-only cards — you cannot change the host, credentials or TLS settings here; that is the administrator’s responsibility.'),
        ul(
          'Database — the Exasol host the connection points at, shown as “Database: host:port”.',
          'LLM — shown when a model server is attached; it enables the AI Documentation feature.',
        ),
        tip('Database passwords and LLM API keys are encrypted at rest and never sent to the browser — the app only receives host, port, schema and whether an LLM is attached.'),
      ],
    },
    {
      heading: 'Connecting',
      body: [
        p('Tap a connection card to connect; tap it again to disconnect. Only one connection is active at a time. Disconnecting clears all loaded data — project, map, KPIs and filters all reset.'),
        p('Up to two coloured dots appear on the active connection. The first is the database state: green when connected, orange while connecting or after a failure. The second appears only when an LLM server is attached: blue when the model server is reachable, orange when it is not.'),
        tip('Use the ↻ button in the Connections header to refresh the list after an administrator has just granted you a new connection.'),
      ],
    },
    {
      heading: 'Power users: manage your own connections',
      body: [
        p('If an administrator has given your account the power role, a ＋ button appears in the Connections header. Use it to create a connection — Exasol host, credentials, optional TLS and an optional LLM server — right from the app, and to tick the users it should be assigned to.'),
        p('You manage only the connections you create: an ✎ button appears on those cards so you can edit or delete them and change who they are assigned to. Every new connection is automatically assigned to you, so you can connect to it immediately. Passwords and API keys you enter are encrypted at rest and, once saved, are never sent back to the browser — leave those fields blank when editing to keep the stored secret unchanged.'),
        p('The editor has two tabs. “Database / LLM Details” holds the connection fields; it can also create a fresh process-mining schema for you — enter a schema name and the database credentials, then use “Create schema & tables” to build the schema and the required tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they don’t already exist.'),
        p('The “Demo Content” tab generates a ready-made dataset into the schema. Two are offered: a Retail dataset (📚 “Online Bookstore” — a synthetic order lifecycle with a returns flow and a flaky bank-transfer path) and a Finance/Insurance dataset (💶 “Online Credit Application” — bank/affiliate intake, an application-check rework loop, credit assessment, and score- and sum-driven approval with agent-review loops, ending in payment or rejection). For either, enter the schema and how many journeys, then Generate; it creates the schema and tables as needed and loads the journeys into that dataset’s own project (others are left untouched).'),
        warn('Creating a schema or generating demo data needs a database account with CREATE SCHEMA / CREATE TABLE (and, for demo data, INSERT) rights. Only your database administrator can grant those — the application cannot authorise you.'),
        tip('Use Test in the editor to check the database (and LLM, if set) before saving.'),
      ],
    },
    {
      heading: 'Demo event-ID format',
      body: [
        p('In both demo datasets the stored EVENT_ID — the case key that ties a journey’s rows together — is the MD5 hash of a simple synthetic reference: the dataset prefix plus a 1-based, zero-padded 6-digit sequence number. So the first journey uses ORD-000001 / CRA-000001, the second ORD-000002 / CRA-000002, and so on.'),
        code(
          'Online Bookstore (BOOKSTORE):     EVENT_ID = md5("ORD-000001"), md5("ORD-000002"), …\n' +
            'Online Credit Application (CREDIT): EVENT_ID = md5("CRA-000001"), md5("CRA-000002"), …\n' +
            '\n' +
            '# reproduce a specific ID from a shell:\n' +
            "printf 'ORD-%06d' 1 | md5      # macOS  →  the stored 32-char hex EVENT_ID\n" +
            "printf 'CRA-%06d' 42 | md5sum  # Linux",
        ),
        tip('In the Individual Journey view you can type the friendly reference (e.g. ORD-000001) straight into the Event ID field — it is MD5-hashed for you — or paste a raw 32-character hash.'),
      ],
    },
    {
      heading: 'No connections listed?',
      body: [
        p('An empty Connections list means no connection has been assigned to your account yet. Ask an administrator to grant you access from the admin interface (Database Connections tab) — or, if you are a power user, create one with the ＋ button.'),
      ],
    },
  ],
}

// ── Administration ──────────────────────────────────────────────────────────

const administration: HelpTopic = {
  id: 'administration',
  title: 'Administration',
  subtitle: 'The admin interface: TLS, users, connections and directory sign-in',
  icon: '⚙︎',
  sections: [
    {
      heading: 'The admin interface',
      body: [
        p('A separate administration interface runs on its own port (8090 by default) and is where all security and access is configured. It has its own sign-in and admits administrators only.'),
        p('On first run it seeds a local administrator — Administrator / Administrator — and prompts you to change the password. Local admin accounts always work as a break-glass route, even if a directory is later misconfigured.'),
        tip('The admin interface is organised into five tabs: App Control (restart the servers), TLS / SSL, Users, Database Connections and Directory (LDAP).'),
      ],
    },
    {
      heading: 'TLS / SSL',
      body: [
        p('Choose how connections are accepted: Off (HTTP only), Optional (HTTP and HTTPS together) or Required (HTTPS only). Generate a self-signed certificate or upload your own PEM certificate and key, then mark one active.'),
        p('The main app and the admin interface both follow this one mode and share the same active certificate — the app on ports 8080/8443, the admin on 8090/8453. Changes take effect when the servers restart: the ↻ Restart app server button in the App Control tab rebinds both in place. If a mode needs a certificate but none is active, each server falls back to HTTP so nothing (including the admin itself) is left unreachable.'),
        warn('Certificate private keys are encrypted at rest. Keep the active certificate valid — an expired certificate makes HTTPS clients refuse to connect.'),
      ],
    },
    {
      heading: 'Users & sign-in',
      body: [
        p('The Users tab controls who may sign in to the main application: create local users, enable or disable access, grant or revoke the admin role, and reset local passwords. Only enabled users can sign in.'),
        p('The Require sign-in toggle turns the login gate on or off for the main app (on by default). With it off, the app is open to anyone who can reach it.'),
        def('Power role', 'Make power / Remove power grants the power badge. Power users can create and manage their own database connections from within the main app and assign them to other users — without needing access to this admin interface. They manage only the connections they create; admins still see and manage every connection.'),
        def('Source badge', 'Each user is tagged local or LDAP so you can tell built-in accounts from directory accounts at a glance; the All / Local / LDAP filter narrows the list.'),
      ],
    },
    {
      heading: 'Database Connections',
      body: [
        p('Define each connection here — the Exasol host, port, user, password, schema and TLS options, plus an optional OpenAI-compatible LLM server — and assign it to one or more users. Each user then sees only the connections assigned to them.'),
        p('Use Test connection to verify the database (and LLM) before saving. Leaving a password or API-key field blank on an existing connection keeps the stored value. Secrets never leave the admin interface.'),
        p('“Create schema & tables” provisions a fresh process-mining schema — it creates the named schema and the required tables (PROJECTS, JOURNEYS, STEPS, METAS, NOTES) if they are missing, using the credentials entered.'),
        warn('This needs a database account with CREATE SCHEMA and CREATE TABLE privileges. Those can only be granted by the database administrator — the application cannot grant them.'),
      ],
    },
    {
      heading: 'Directory (LDAP / Active Directory)',
      body: [
        p('When enabled, the main-app login also accepts directory accounts via search + bind: a read-only service account searches the base DN for the login name, then the app re-binds as that user with the supplied password.'),
        ul(
          'Set the server URI (ldap:// or ldaps://, with optional StartTLS), the service-account bind DN and password, the base DN, and the user filter and attributes.',
          'Test server connection checks the server and service bind alone; Test a user login also resolves and signs in a directory account.',
          'On first successful sign-in a directory user is created locally as a plain, enabled account, so you can assign connections and, if you wish, the admin role.',
        ),
        p('While a directory is configured, the app’s sign-in panel shows a small status light — green when the directory server answers a connection test, red when it does not. The light is hidden entirely when no directory is configured.'),
        p('By default the admin interface stays local-only. Tick “Also allow directory sign-in to this admin interface” to let directory accounts sign in here too — but only after one has been promoted to admin in the Users tab. Local administrators always work regardless, as a break-glass route.'),
        tip('Admin is never granted from the directory — a directory user stays a normal user until a local admin promotes them.'),
      ],
    },
  ],
}

// ── Chart views ───────────────────────────────────────────────────────────────

const chartViews: HelpTopic = {
  id: 'chartviews',
  title: 'Chart Views',
  subtitle: 'Process map, A/B comparison, individual journey and statistics',
  icon: '📊',
  sections: [
    {
      heading: 'A-Chart',
      body: [
        p('The primary process map. Shows all journeys matching the current filter set as an aggregated directly-follows graph; arrow thickness reflects the selected transition metric. When a project is first selected, A-Chart loads automatically using the last 30 days of data.'),
        tip('A date slider sits above the map. In Range mode it has two thumbs; in Day mode a single thumb selects one calendar day. Switch modes in Configuration → Date slider.'),
      ],
    },
    {
      heading: 'B-Chart',
      body: [
        p('An independent second process map with its own filter set — use it to explore a different segment (date window, step selection, or meta value). B-Chart starts empty: apply filters and tap Apply, or use the Load button on its empty state.'),
      ],
    },
    {
      heading: 'A/B Comparison',
      body: [
        p('Splits the main area vertically: A-Chart on the left, B-Chart on the right, both visible at once. The sidebar filters operate on the active side — switch it by tapping a panel header or the A/B segmented control at the top of the Filters section. The active panel shows a pencil icon and an “editing” label.'),
        def('Valve (⇄ on the divider)', 'Open: both panels share one viewport, so pan, zoom, reset and node drags mirror instantly. Closed: each panel moves independently; closing snapshots A’s current view into B so they start aligned before diverging. A is always the master.'),
        def('Copy layout (⧉ in A’s header)', 'Transfers A’s complete viewport — zoom, pan and every node position — to B in one tap.'),
        p('A Process Similarity badge floats between the panels, showing the Q score coloured green/blue/red. It refreshes automatically whenever you apply filters or move a date slider in either panel. See the Process Similarity chapter.'),
      ],
    },
    {
      heading: 'Individual Journey',
      body: [
        p('Shows the complete step sequence for a single journey identified by EVENT_ID. The Filters section becomes an Event ID field: type a source identifier (e.g. ORD-000001) or a raw 32-character hash and press Return. Any input that is not already a hash is MD5-hashed automatically before querying, so you never compute a hash by hand.'),
        tip('A live suggestion dropdown appears as you type. Each EVENT_ID keeps its own saved node layout.'),
      ],
    },
    {
      heading: 'Statistics',
      body: [
        p('Analyses all journey routes matching the current filters — which it always inherits from Chart A. A Routes / Analytics toggle switches between a searchable, sortable, paginated table of distinct journey variants (with a journeys-over-time chart) and a set of visualisations: the duration histogram, step traffic, and a transition heat map.'),
        tip('If you change a filter after loading, an orange “Filters changed since last load” banner appears with a one-tap Reload button. The journeys-over-time granularity is chosen automatically: ≤14 days → daily, ≤90 days → weekly, otherwise monthly.'),
      ],
    },
  ],
}

// ── Filters ───────────────────────────────────────────────────────────────────

const filters: HelpTopic = {
  id: 'filters',
  title: 'Filters',
  subtitle: 'Metrics, date range, steps, score and meta filters',
  icon: '⛃',
  sections: [
    {
      heading: 'Transition metrics',
      body: [
        p('The Metrics section controls which value drives the thickness, opacity, colour and label of each transition arrow.'),
        def('Count', 'Number of times this transition occurred. The default, always available.'),
        def('Avg Time', 'Average elapsed time between the two steps, shown as a readable duration (4m, 1.2h, 3.5d).'),
        def('Min / Max Time', 'Shortest / longest observed elapsed time for this transition.'),
        def('Std Dev', 'Standard deviation of elapsed times — higher values indicate inconsistent transition durations.'),
        tip('Each chart view stores its own metric selection. Each metric has its own colour scale — click the colour legend at the bottom-right of the map to configure them.'),
      ],
    },
    {
      heading: 'Journey-level filters',
      body: [
        p('Every filter works at journey (case) level, so a journey either qualifies in full or not at all.'),
        def('Date range', 'Journeys with at least one event inside the window. Adjustable from the slider above the map.'),
        def('Include Steps', 'Show only journeys that pass through any selected step.'),
        def('Exclude Steps', 'Remove every journey that passes through any selected step. A step chosen for Include is automatically disabled for Exclude, and vice versa.'),
        def('Num Steps', 'Keep journeys whose total step count is within the range.'),
        def('Journey Time', 'Keep journeys whose first-to-last span is within the range.'),
        def('Journey Score', 'Keep journeys whose summed step scores are within the range. Negative scores are supported — drag the right handle below zero to isolate problem paths.'),
        def('Meta 1–3', 'Case-level case-insensitive contains search, with autocomplete drawn from distinct values in the database.'),
      ],
    },
    {
      heading: 'Applying, resetting and saving',
      body: [
        p('Filters are not applied automatically. Three buttons sit at the bottom of the section:'),
        def('Reset', 'Restores all filters to the project defaults.'),
        def('Save Preset…', 'Captures the current filter state as a named preset (see the Filter Presets chapter).'),
        def('Apply', 'Reloads the map with the current settings. In A/B Comparison only the active side reloads.'),
        p('Filtered Journeys shows matches for the active filters; Total Journeys always reflects the unfiltered project count.'),
      ],
    },
  ],
}

// ── Filter presets ────────────────────────────────────────────────────────────

const filterPresets: HelpTopic = {
  id: 'filterpresets',
  title: 'Filter Presets',
  subtitle: 'Save and reapply named filter configurations',
  icon: '🔖',
  sections: [
    {
      heading: 'What is a preset?',
      body: [
        p('A preset captures a complete snapshot of every filter dimension — date range, included/excluded steps, meta values, step-count, journey-time and score bounds — under a name of your choice. Presets are stored per project, persist between sessions, and are included in Backup & Restore.'),
      ],
    },
    {
      heading: 'Saving, applying, managing',
      body: [
        p('Configure the filters you want, then tap “Save Preset…” between the Reset and Apply buttons and give it a name. The state is captured at that moment — later filter changes do not update the preset.'),
        p('Every chart header shows a Presets picker. Choose a preset to restore all its settings instantly; the chart reloads and the date slider updates to the preset’s window. In A/B Comparison each panel has its own independent Presets picker, so you can apply different presets to A and B at once.'),
        tip('Rename and delete a preset from the small ✎ / 🗑 buttons next to it in the sidebar Presets list.'),
      ],
    },
  ],
}

// ── Process map ───────────────────────────────────────────────────────────────

const processMap: HelpTopic = {
  id: 'processmap',
  title: 'Process Map',
  subtitle: 'Navigation, nodes, groups and context actions',
  icon: '🗺',
  sections: [
    {
      heading: 'Reading the map',
      body: [
        p('Each node is a distinct process step. Arrows show transitions; thickness and opacity reflect the selected transition metric relative to the highest value on the map. The label shows the value for the active metric — a plain number for Count, or a readable duration for time-based metrics.'),
      ],
    },
    {
      heading: 'Connection colouring',
      body: [
        p('When “Colorise edges by weight” is on, each arrow is tinted using the colour scale configured for the active metric, from the low-end colour (few / short) to the high-end colour (many / long). Thickness always encodes the value independently of colour.'),
        def('Per-metric scales', 'Each of the five metrics has its own scale. Defaults: Count → green, Avg Time → orange, Min Time → blue, Max Time → red, Std Dev → purple.'),
        tip('Click the colour legend in the bottom-right corner of the map to open the wizard and pick a scale for each metric, with a live preview. “Reset to defaults” restores the built-in scales.'),
      ],
    },
    {
      heading: 'Start and end markers',
      body: [
        def('Green arrow (entry)', 'Appears above every start node — a step with no incoming transitions.'),
        def('Orange arrow (exit)', 'Appears below every end node — a step with no outgoing transitions.'),
        p('When a step belongs to a group, both markers are drawn outside the group’s dashed border so they stay visible.'),
      ],
    },
    {
      heading: 'Navigating & moving nodes',
      body: [
        ul(
          'Scroll / pinch to zoom, drag the background to pan, double-click to fit the graph to the window.',
          'Drag a node to reposition it — saved per project and per chart view; positions snap to a 20 pt grid.',
          'Drag a group box to move all its members at once.',
          '↺ discards custom positions and reverts to the automatic layout.',
          '⤢ fits the graph; the ± buttons zoom precisely.',
        ),
        tip('The quality of the automatic layout depends on the “Optimise layout” toggle in Configuration — when on, crossing minimisation produces a cleaner arrangement on complex graphs.'),
      ],
    },
    {
      heading: 'Node context menu',
      body: [
        p('Click a node to open a small action card:'),
        def('Require in journeys', 'Adds the step to Include Steps and reloads.'),
        def('Exclude from journeys', 'Adds the step to Exclude Steps and reloads.'),
        def('Show Notes', 'Opens the notes interface for this node (see the Notes chapter).'),
        def('Show description', 'Displays the full DESCRIPTION text for the step, when it differs from the name.'),
      ],
    },
    {
      heading: 'Node appearance & groups',
      body: [
        p('Colours and shapes (stadium / round / hex / circle) come from the STEPS table and are editable in Configuration → Steps. An orange dot marks an end-of-process step; a score badge in the top-left is green for positive, red for negative, blue for zero. A yellow ✎ badge marks a node with a note.'),
        p('Steps sharing a BELONGS_TO value are wrapped in a dashed, coloured group box with a name pill. The +/− badge on the box collapses or expands it — collapsed groups sum connection counts and weight-average the times. “Groups start” in Configuration controls whether groups load Expanded, Collapsed, or in their last Persisted state.'),
      ],
    },
  ],
}

// ── KPI panel ─────────────────────────────────────────────────────────────────

const kpi: HelpTopic = {
  id: 'kpi',
  title: 'KPI Panel',
  subtitle: 'Journey counts, durations and score tiles',
  icon: '📇',
  sections: [
    {
      heading: 'The tiles',
      body: [
        def('Total Journeys', 'Distinct journeys in the project with no filters applied. Does not change when you adjust filters.'),
        def('Filtered Journeys', 'Distinct journeys matching all current filters — the population the map visualises.'),
        def('Shortest / Avg / Longest Journey', 'Fastest, mean and slowest journey duration in the filtered set, first event to last.'),
        def('Std Dev', 'Standard deviation of journey durations. Low = most journeys take a similar time; high = durations vary widely.'),
        def('Graph Value', 'Sum of (step score × visit count) for every scored node on the map. Visit count is the larger of a node’s incoming and outgoing transition occurrences, so start and end nodes are handled correctly. A higher value means high-scoring steps are visited frequently.'),
        def('Process Goodness', 'A composite quality score for the whole process. Rewards paths where high-scoring steps are reached efficiently and penalises slow or low-scoring routes, with a coverage factor. See the Process Goodness chapter for the formula and worked examples.'),
        def('Process Similarity', 'A/B mode only — floats between the panels. Compares the two filtered processes; see the Process Similarity chapter.'),
      ],
    },
    {
      heading: 'Behaviour',
      body: [
        p('The strip and the date slider appear only once a chart has loaded data, and are hidden on launch, after disconnecting, and on any view not yet loaded. Tap the chevron handle to collapse the strip — the journey counts then appear inline in the handle bar. Reorder tiles and toggle their visibility in Configuration → KPIs.'),
        tip('In A/B Comparison, each panel has its own KPI strip. The Process Goodness tile is coloured green when this panel’s value beats the other, red when lower, blue when equal within 0.005.'),
      ],
    },
  ],
}

// ── Process Goodness (full fidelity) ──────────────────────────────────────────

const processGoodness: HelpTopic = {
  id: 'processgoodness',
  title: 'Process Goodness',
  subtitle: 'How the quality score is calculated',
  icon: '◔',
  sections: [
    {
      heading: 'What it measures',
      body: [
        p('Process Goodness is a single number that summarises how well your process is performing across all journeys matching the current filters. It combines three ideas into one score:'),
        ul(
          'Quality — do journeys pass through high-scoring steps?',
          'Efficiency — are journeys short, or do they take a long time?',
          'Coverage — how large a fraction of total journeys do the current filters capture?',
        ),
        p('Higher values are better. A positive score means the process delivers net value relative to its time cost. A negative score means slow, low-scoring routes are dragging overall quality down.'),
        tip('Process Goodness is only shown when at least one step has a SCORE value configured in the STEPS table. If no scores are set, the tile is hidden.'),
      ],
    },
    {
      heading: 'The formula',
      body: [
        p('The score is computed in two stages. First, a raw goodness is calculated across all distinct path patterns:'),
        code('raw = Σ (freq / total) × (sum_of_scores / √n − 0.01 × avg_duration)'),
        p('Where the sum runs over every distinct path pattern in the filtered set. Then a coverage factor is applied:'),
        code('Process Goodness = raw × (filtered_journeys / total_journeys)^0.5'),
        p('That is all. Everything else is just understanding what each symbol means — which the following sections explain one by one.'),
      ],
    },
    {
      heading: 'Inside the formula: each term explained',
      body: [
        def('freq / total', 'The relative frequency of this path pattern. A path taken by 80 out of 100 journeys has freq/total = 0.80. More common paths have a stronger influence on the final score — the formula is a weighted average, not a simple average.'),
        def('sum_of_scores', 'The sum of SCORE values (from the STEPS table) for every step in this path. If a step has no score it contributes zero. A path through high-value steps produces a large positive sum; a path through penalised steps (negative scores) can produce a negative sum.'),
        def('√n  (alpha = 0.5)', 'The square root of the number of steps in the path. Dividing by √n means longer paths must earn proportionally more total score to keep up with shorter paths — but the penalty grows slowly (as a square root, not linearly). A 4-step path divides by 2; a 9-step path divides by 3. This discourages unnecessary detours without harshly punishing genuinely complex processes.'),
        def('0.01 × avg_duration', 'A time penalty. avg_duration is the average total journey time in seconds for this path pattern. Multiplying by 0.01 means every 100 seconds of journey time costs 1.0 point. Fast paths are rewarded; slow paths are penalised. The constant 0.01 is chosen so that moderate durations (a few minutes) impose a small but noticeable penalty.'),
        def('(filtered / total)^0.5  (gamma = 0.5)', 'The coverage factor. If your current filters capture only half of all journeys, this term equals √0.5 ≈ 0.71 and reduces the score by about 29 %. A goodness score computed from a narrow slice of data should be taken with more caution than one computed from the full population. When no filters are active, coverage = 1.0 and the factor has no effect.'),
        tip('All fixed constants — alpha=0.5, time_penalty=0.01, gamma=0.5 — are embedded in the formula. They reflect a balanced default and are not adjustable in the current version.'),
      ],
    },
    {
      heading: 'Example 1 — two paths, short vs. long',
      body: [
        p('A digital checkout process has 100 orders. 85 take the direct path; 15 use a coupon step.'),
        code(
          `Path A  (85 journeys): Browse → Cart → Pay → Confirm
  Scores: 2 + 3 + 10 + 10 = 25    Steps: 4    Avg duration: 30 s

Path B  (15 journeys): Browse → Cart → Coupon → Pay → Confirm
  Scores: 2 + 3 + 1 + 10 + 10 = 26    Steps: 5    Avg duration: 60 s`,
        ),
        p('Calculation for Path A:'),
        code(
          `quality   = 25 / √4 = 25 / 2     = 12.50
time cost = 0.01 × 30            =  0.30
path score = 12.50 − 0.30        = 12.20
weighted   = 0.85 × 12.20        = 10.37`,
        ),
        p('Calculation for Path B:'),
        code(
          `quality   = 26 / √5 ≈ 26 / 2.24  = 11.61
time cost = 0.01 × 60            =  0.60
path score = 11.61 − 0.60        = 11.01
weighted   = 0.15 × 11.01        =  1.65`,
        ),
        p('Combined result (all 100 journeys in filter, 100 total):'),
        code(
          `raw = 10.37 + 1.65 = 12.02
coverage = 100 / 100 = 1.0    →  factor = √1.0 = 1.00

Process Goodness = 12.02 × 1.00 = +12.02`,
        ),
        tip('Notice that Path B contributes slightly less per journey (11.01 vs 12.20) even though it collects one extra score point. The longer path and slower duration partially offset the extra point — the formula captures this tradeoff automatically.'),
      ],
    },
    {
      heading: 'Example 2 — a failed-payment path with negative scores',
      body: [
        p('The same checkout process, but now 10 orders encounter a payment failure and are refunded. Step scores: Pay Failed = −10, Refund = −5.'),
        code(
          `Path A  (80 journeys): Browse → Cart → Pay → Confirm
  Scores: 25    Steps: 4    Avg duration: 30 s    (same as before)

Path B  (10 journeys): Browse → Cart → Coupon → Pay → Confirm
  Scores: 26    Steps: 5    Avg duration: 60 s    (same as before)

Path C  (10 journeys): Browse → Cart → Pay → Pay Failed → Refund
  Scores: 2 + 3 + 10 + (−10) + (−5) = 0    Steps: 5    Avg duration: 90 s`,
        ),
        p('Path C contributes:'),
        code(
          `quality   = 0 / √5 = 0
time cost = 0.01 × 90 = 0.90
path score = 0 − 0.90        = −0.90
weighted   = 0.10 × (−0.90)  = −0.09`,
        ),
        p('Combined result:'),
        code(
          `Path A weighted: 0.80 × 12.20 =  9.76
Path B weighted: 0.10 × 11.01 =  1.10
Path C weighted:              = −0.09

raw = 9.76 + 1.10 − 0.09 = 10.77
coverage = 1.0

Process Goodness = +10.77   (was +12.02 before failures appeared)`,
        ),
        p('The failed-payment path reduces the score from +12.02 to +10.77 — a drop of 1.25 points — even though it affects only 10 % of journeys. The combined effect of zero quality score and additional time makes it a net negative contributor.'),
        tip('Use this pattern to detect problem paths. When you notice a sudden drop in Process Goodness between two date periods, filter to isolate paths through specific problem steps — the score will confirm whether those paths are truly responsible for the decline.'),
      ],
    },
    {
      heading: 'Example 3 — the coverage penalty when filtering',
      body: [
        p('You apply a region filter — “Europe only” — and now only 40 of the 100 total orders match. Within those 40 orders there are no payment failures, so the raw goodness is the same clean +12.02.'),
        p('However, the coverage factor now kicks in:'),
        code(
          `coverage = 40 / 100 = 0.40
factor   = √0.40 ≈ 0.632

Process Goodness = 12.02 × 0.632 ≈ +7.60`,
        ),
        p('The filtered Europe result (+7.60) looks worse than the global result (+12.02), not because Europe performs worse, but because the filter captures a smaller proportion of the total population. The score reflects both quality and representativeness.'),
        tip('To compare two segments fairly, switch to A/B Comparison mode: set A to one segment and B to the other. The Process Goodness tile in each panel applies the same formula independently, so the scores are directly comparable even with different journey counts.'),
      ],
    },
    {
      heading: 'Requirements and limitations',
      body: [
        ul(
          'At least one step must have a non-zero SCORE value in the STEPS table. Without scores the tile is hidden.',
          'The query groups journeys by path pattern — on very large, heavily filtered datasets it may take several seconds. A 30-second timeout applies; if it expires the tile shows “—”.',
          'Average duration per path pattern is used as the time component. Individual journeys may differ from this average.',
          'Steps with no SCORE set contribute 0 to the quality sum — they neither help nor hurt.',
          'The score can be negative when slow, low-scoring paths dominate the filtered set.',
        ),
        warn('Process Goodness is a relative indicator, not an absolute benchmark. Use it to spot trends over time, compare segments in A/B mode, or monitor the impact of process changes — not as a standalone pass/fail threshold.'),
      ],
    },
  ],
}

// ── Process Similarity (full fidelity) ────────────────────────────────────────

const processSimilarity: HelpTopic = {
  id: 'processsimilarity',
  title: 'Process Similarity',
  subtitle: 'How Q(T₁, T₂) compares two filtered processes',
  icon: '⇄',
  sections: [
    {
      heading: 'What it measures',
      body: [
        p('Process Similarity Q(T₁, T₂) is a single number between 0 and 1 that answers: how behaviourally alike are the two process views loaded in A-Chart and B-Chart?'),
        p('A score of 1.0 means the two processes are identical — every variant is explained equally well by both graphs and the same scored steps are visited in the same proportion. A score of 0.0 means they share almost nothing. Values in between indicate partial overlap.'),
        p('Unlike Process Goodness, which measures how good a single process is, Process Similarity is a comparison metric. Use it to confirm that two filter segments really are behaving differently, or to verify that a process change has had a measurable effect.'),
        tip('Process Similarity only appears in A/B Comparison mode, as a floating badge between the two panels. It refreshes automatically whenever you apply filters or move a date slider in either panel.'),
      ],
    },
    {
      heading: 'The formula',
      body: [
        p('Q is a weighted average of three components, each between 0 and 1:'),
        code('Q(T₁, T₂) = 0.4 · Q_var  +  0.4 · Q_nodes  +  0.2 · Q_cov'),
        def('Q_var  (weight 40 %)', 'Variant alignment agreement. Measures how consistently both graphs explain the same journey variants. If both graphs handle a variant equally (both replay it perfectly, or both fail equally), Q_var is high. If one graph handles a variant much better than the other, Q_var is low.'),
        def('Q_nodes  (weight 40 %)', 'Node agreement weighted by importance. A Jaccard-style ratio comparing which scored steps are actually visited — under each graph — per variant. Steps with a higher absolute score value count more. If both graphs visit the same high-value steps in the same variants, Q_nodes approaches 1.'),
        def('Q_cov  (weight 20 %)', 'Joint coverage. The fraction of variant frequency that is explained perfectly (zero missing edges) by both graphs simultaneously. A high value means most journeys fit neatly into both process models.'),
        tip('The 40/40/20 weights reflect that structural similarity (Q_var) and scored-step agreement (Q_nodes) are equally important, while coverage is a useful but secondary signal.'),
      ],
    },
    {
      heading: 'Alignment cost — the key building block',
      body: [
        p('For each journey variant (a specific sequence of steps), the formula computes an alignment cost for each graph:'),
        code('cost_T(v) = missing_edges / total_edges_in_variant'),
        p('A “missing edge” is a consecutive step pair in the variant that does not appear as a transition in the graph. If all transitions exist, cost = 0 (perfect fit). If half are missing, cost = 0.5. A variant with only one step (no edges) is skipped.'),
        p('This is a practical approximation of formal process-mining alignment. It runs in linear time per variant and requires no external solver, making it fast enough to run automatically on every panel reload.'),
        tip('The variant set is capped at 500 per side (1 000 combined). When the cap is exceeded the badge is hidden rather than showing a misleading score computed from a biased sample.'),
      ],
    },
    {
      heading: 'Example 1 — nearly identical segments',
      body: [
        p('A-Chart shows European orders; B-Chart shows North American orders. Both regions follow almost the same checkout process.'),
        code(
          `Variant A  (90 % of journeys, both sides):
  Browse → Cart → Pay → Confirm
  Edges exist in both graphs → cost_A = 0,  cost_B = 0

Variant B  (10 % of journeys, EU only):
  Browse → Cart → Coupon → Pay → Confirm
  All edges in A-graph; Coupon→Pay missing in B-graph
  cost_A = 0,  cost_B = 1/4 = 0.25`,
        ),
        p('Weighting by frequency, Variant A (90 %) agrees perfectly while Variant B (10 %) diverges:'),
        code(
          `Weighted Q_var ≈ 0.90 × 1.0 + 0.10 × 0.0 = 0.90

Assume scored steps: Pay = +10, Confirm = +10 (both graphs)
Q_nodes ≈ 0.95  (Coupon step has no score, so its absence barely matters)
Q_cov   = 0.90  (90 % of frequency fits both perfectly)

Q = 0.4 × 0.90 + 0.4 × 0.95 + 0.2 × 0.90
  = 0.36 + 0.38 + 0.18 = 0.92  → green`,
        ),
        tip('A score of 0.92 correctly reflects that EU and North America are very similar processes — only the coupon path distinguishes them.'),
      ],
    },
    {
      heading: 'Example 2 — same period, different quality paths',
      body: [
        p('A-Chart shows the standard process (no failures); B-Chart shows the same date range filtered to orders that included a “Pay Failed” step. These are structurally different populations.'),
        code(
          `Variant A  (100 % of A-side): Browse → Cart → Pay → Confirm
  All edges in A-graph (cost_A = 0)
  'Pay → Confirm' missing from B-graph  (cost_B = 1/3 ≈ 0.33)

Variant B  (100 % of B-side): Browse → Cart → Pay → Pay Failed → Refund
  'Pay → Confirm' missing from A-graph  (cost_A = 1/3 ≈ 0.33)
  All edges in B-graph  (cost_B = 0)

Scored steps: Pay = +5, Confirm = +10, Pay Failed = −10, Refund = −5`,
        ),
        code(
          `Q_var   = 0.00   (each side fits only its own variant)
Q_nodes ≈ 0.45   (high-value steps differ between the two populations)
Q_cov   = 0.00   (neither variant fits both graphs perfectly)

Q = 0.4×0.00 + 0.4×0.45 + 0.2×0.00 = 0.18  → red`,
        ),
        p('A score of 0.18 correctly signals strong divergence — the happy-path and failure-path populations are fundamentally different processes.'),
      ],
    },
    {
      heading: 'Example 3 — before and after a process change',
      body: [
        p('A-Chart shows January (before a redesign); B-Chart shows February (after). The redesign merged two slow approval steps into one. Most variants are shared but with different graph structure.'),
        code(
          `Shared variant (70 %): Browse → Submit → Approve → Complete
  Both graphs contain these edges → cost_A = 0, cost_B = 0

Old variant (30 %, Jan only): Browse → Submit → Review → Approve → Complete
  cost_A = 0  (all edges in Jan graph)
  'Submit→Review' and 'Review→Approve' missing from Feb graph
  cost_B = 2/4 = 0.50

Scored steps: Approve = +8, Complete = +10`,
        ),
        code(
          `Weighted Q_var = 0.70×1.0 + 0.30×0.0 = 0.70
Q_nodes ≈ 0.82   (Review step has no score, so its absence barely hurts)
Q_cov   = 0.70   (70 % of frequency fits both graphs perfectly)

Q = 0.4×0.70 + 0.4×0.82 + 0.2×0.70
  = 0.28 + 0.33 + 0.14 = 0.75  → green`,
        ),
        p('A score of 0.75 reflects that the two periods are broadly similar — the core path is unchanged — but the old Review step creates a measurable divergence. Green signals the processes are still recognisably the same, while a value below 0.90 confirms the redesign did introduce a structural difference.'),
        tip('Use this pattern to validate process changes: a Q that stays near 1 after a change means little behavioural effect; a Q that drops toward 0.5 or below confirms a meaningful structural shift.'),
      ],
    },
    {
      heading: 'Colour thresholds and limitations',
      body: [
        ul(
          'Green: Q ≥ 0.70 — the two processes are behaviourally similar.',
          'Blue: 0.30 ≤ Q < 0.70 — moderate similarity; some paths are shared, others differ.',
          'Red: Q < 0.30 — strong divergence; fundamentally different behaviour.',
        ),
        warn('Process Similarity is a relative indicator, not an absolute benchmark. It depends on which steps have SCORE values — if none do, Q_nodes defaults to 1.0 and only Q_var and Q_cov contribute. It is also sensitive to the route limit.'),
        ul(
          'The practical guard caps input at 500 variants per side (1 000 combined). When the cap is hit the badge is hidden.',
          'Alignment cost is an edge-coverage approximation, not a formal Petri-net alignment. It may slightly overestimate similarity for processes with loops or repeated steps.',
          'Q is symmetric: Q(A, B) = Q(B, A). The same value appears for both panels.',
        ),
      ],
    },
  ],
}

// ── Simulation (full fidelity) ────────────────────────────────────────────────

const simulation: HelpTopic = {
  id: 'simulation',
  title: 'Simulation',
  subtitle: 'Synthetic process data from a calibrated Markov model',
  icon: '🎲',
  sections: [
    {
      heading: 'What is simulation?',
      body: [
        p('The Simulation view generates synthetic event logs that statistically resemble your real process. It builds a first-order Markov chain from the currently loaded process graph, then walks that chain to produce journeys with the same three fields your database contains: a journey identifier, a step name, and a timestamp.'),
        p('Every synthetic journey follows the routing probabilities and timing distributions observed in your actual data. This makes the generated log useful for load-testing, what-if analysis, training-data generation, or simply exploring “what would 10 000 more journeys through this process look like?”'),
        tip('The simulation uses the process graph currently loaded in Chart A, including any date-range and step filters. Apply your desired filters before running to calibrate the model on a specific slice of your data.'),
      ],
    },
    {
      heading: 'How the model is calibrated',
      body: [
        p('The calibration algorithm reads three things from the displayed process graph:'),
        def('Transition probabilities', 'For every step with outgoing transitions, the occurrence counts are normalised to probabilities. A step with 600 transitions to “Approve” and 400 to “Reject” routes 60 % of simulated journeys to Approve and 40 % to Reject.'),
        def('Duration distributions', 'Each directed edge carries an average duration and a standard deviation from the real data. The simulator fits a lognormal distribution to these two numbers and samples from it to advance the clock on each transition. Lognormal is the correct shape for process durations: strictly positive and right-skewed, matching the long tail of slow cases seen in practice.'),
        def('Start steps', 'Steps whose incoming frequency is less than 20 % of their outgoing frequency are identified as likely entry points. Their relative frequency as first steps is used to sample the opening step of each journey.'),
        p('If an edge has timing data in only one direction (average without standard deviation, or vice versa), the simulator uses the available value only. If no timing data is present for an edge, a one-hour lognormal is used as a default. Start steps are always identified from the original graph before exclusions, so removing a step never creates a false entry point.'),
      ],
    },
    {
      heading: 'Arrival process',
      body: [
        p('New journeys are born according to a Poisson process: the gap between consecutive journey start times is drawn from an exponential distribution parameterised by “Average inter-arrival (hours)”. This is the standard model for arrivals in queueing theory and discrete-event simulation.'),
        p('A Poisson process is memoryless: knowing that no journey started in the last two hours tells you nothing about when the next will start. This correctly models processes where cases are independently initiated — order placements, patient admissions, support tickets, and so on.'),
        def('Average inter-arrival (hours)', 'The mean number of hours between consecutive journey start times. A value of 1.0 means one new journey starts every hour on average. It controls the spread of timestamps in the exported CSV, but does not affect routing or cycle times.'),
        tip('To estimate the correct rate, check the “Journeys over time” chart in the Statistics view: divide the journey count by the time span in hours.'),
      ],
    },
    {
      heading: 'Simulation parameters',
      body: [
        def('Journey Count', 'How many complete journeys to generate. Higher counts produce more stable variant distributions and smoother histograms but take longer. For a first run, 200–500 is usually enough to see the dominant process shape.'),
        def('Start Date', 'The date assigned to the first simulated journey’s opening event. Subsequent events are timestamped relative to this anchor using the inter-arrival times and step durations.'),
        def('Max Steps per Journey', 'Hard cap on the number of steps per journey — prevents rework loops from running forever. If a journey hits the cap it is included as-is, with a potentially incomplete path. The default (60) suits most real-world processes.'),
        tip('If you see many journeys with exactly 60 steps in the Variants table, the Max Steps cap is being hit. Increase it if your process genuinely contains long rework loops, or add the looping step to the Excluded Steps list.'),
      ],
    },
    {
      heading: 'Excluded and required steps',
      body: [
        def('Excluded steps', 'Removed from the Markov model entirely before simulation begins — all transitions to and from them are discarded. Use this to model a process improvement, e.g. removing a manual approval step to see the flow when it is automated away. Steps that become unreachable as a result are automatically excluded too, transitively.'),
        def('Required steps', 'A post-simulation filter: only journeys that visit every required step at least once are kept. The engine generates the full configured count and then discards those that do not qualify, so the reported total can be lower than the configured Journey Count if the required steps are rare.'),
        p('The two lists are mutually exclusive — a step chosen as excluded cannot also be required.'),
      ],
    },
    {
      heading: 'Worked example — a fork process',
      body: [
        p('Suppose the observed A-Chart graph is a simple fork: after Start, 70 % of cases go through the Fast branch and 30 % through the Slow branch, then both rejoin at End.'),
        code(
          `Observed transitions (calibration input):
  Start → Fast   occurrences 700   avg 2 min,  sd 30 s
  Start → Slow   occurrences 300   avg 2 min,  sd 30 s
  Fast  → End    occurrences 700   avg 5 min,  sd 1 min
  Slow  → End    occurrences 300   avg 40 min, sd 8 min`,
        ),
        p('The engine derives the Markov model:'),
        code(
          `Start step   : Start   (in/out ratio < 0.2 → entry point)
P(Fast | Start) = 700 / 1000 = 0.70
P(Slow | Start) = 300 / 1000 = 0.30
Fast → End, Slow → End are the only continuations (probability 1.0)

Edge durations → fitted lognormal(μ, σ) per edge, floor 60 s`,
        ),
        p('Running 1 000 journeys, each walk starts at Start, samples Fast or Slow by those probabilities, draws a duration from the fitted lognormal on each edge, and stops at End (an end-of-process step). The output converges to roughly:'),
        code(
          `Variant "Start → Fast → End"   ≈ 700 journeys (70 %)   avg ≈ 7 min
Variant "Start → Slow → End"   ≈ 300 journeys (30 %)   avg ≈ 42 min

Cycle-time histogram: a tall early peak (the Fast branch) and a
smaller, wider hump further right (the Slow branch) — bimodal,
exactly as the two-branch structure predicts.`,
        ),
        tip('Because sampling is random, your counts will vary slightly run to run — around 700/300, not exactly. Raise the Journey Count for a tighter match to the observed proportions. Set the RNG-free expectation by watching the percentages in the Variants tab converge as you increase the count.'),
      ],
    },
    {
      heading: 'What-if example — automating the slow branch',
      body: [
        p('Add “Slow” to the Excluded steps list and run again. The engine removes Start→Slow and Slow→End, then re-normalises: now 100 % of journeys take the Fast branch.'),
        code(
          `After excluding "Slow":
  P(Fast | Start) = 700 / 700 = 1.00

Result: one variant "Start → Fast → End", ~1000 journeys,
avg ≈ 7 min, and a single-peaked (unimodal) cycle-time histogram.`,
        ),
        p('Comparing the two runs quantifies the impact of the improvement: removing the slow branch collapses the bimodal distribution to a single fast peak and cuts the average cycle time dramatically — all without touching the database.'),
        tip('Store each run in a slot (Sim-A / Sim-B), then select them as the A and B data sources in the Sampling section to compare the two synthetic processes side-by-side in A/B Comparison — including a Process Similarity score between them.'),
      ],
    },
    {
      heading: 'Reading the results',
      body: [
        p('After a run, six KPI tiles summarise the output — Journeys, Avg cycle time, Shortest, Longest, Std dev, and Variants — above four tabs:'),
        def('Flow', 'The directly-follows graph of the simulated log, rendered with the same interactive flow chart used everywhere else. Because simulation is probabilistic, this graph resembles but is not identical to the real one — with a small Journey Count, rare edges may not be sampled at all.'),
        def('Variants', 'A ranked table of every distinct path, ordered by frequency, with count, share and average cycle time.'),
        def('Charts', 'A cycle-time distribution histogram and a top-variants bar chart. A unimodal, right-skewed histogram is typical of a well-behaved process; a bimodal shape often signals two fundamentally different paths — check the Variants tab for the split.'),
        def('Event log', 'The raw event rows (JOURNEY_ID, STEP, EVENT_TIME). Export the full log as CSV with the Export button.'),
      ],
    },
    {
      heading: 'Exporting the event log',
      body: [
        p('Export CSV saves the full event log — one row per event, three columns:'),
        code('JOURNEY_ID,STEP,EVENT_TIME'),
        p('The file is structurally identical to a JOURNEYS export from Exasol, so you can import it into another process-mining tool, load it into Excel or pandas, feed it back into an Exasol JOURNEYS table as a test sample set, or use it as labelled training data for ML models.'),
      ],
    },
    {
      heading: 'Limitations and assumptions',
      body: [
        p('The simulator is a first-order Markov model: each routing decision depends only on the current step, not on what came before. If your real process has strong history-dependent routing — for example, cases rejected once behaving very differently on retry — the model will not capture this.'),
        ul(
          'Long-range dependencies and case attributes (META_1–3) are not modelled — there is no concept of a customer segment or region that influences routing.',
          'Resource constraints and queues are not modelled. Cycle times are sampled independently per event; doubling volume does not increase waiting time.',
          'The model calibrates from the visible graph only. If the active filter excludes date ranges or step types, the model reflects only that subset.',
          'Very rare transitions may have unreliable duration estimates — a standard deviation estimated from two or three observations is noisy.',
        ),
        warn('Do not use simulation results as a substitute for real data analysis when making production decisions. The simulation reproduces the statistical structure of your process — but not individual journey behaviour, seasonal effects, or emergent properties from resource contention.'),
      ],
    },
  ],
}

// ── Conformance Check ─────────────────────────────────────────────────────────

const conformance: HelpTopic = {
  id: 'conformance',
  title: 'Conformance Check',
  subtitle: 'Compare the actual process against target norms',
  icon: '🛡️',
  sections: [
    {
      heading: 'What it does',
      body: [
        p('Conformance Check overlays target values (“norms”) on any transition metric and shows, edge by edge, whether the actual process meets them. Switch metrics with the chips at the top — norms are stored per project and per metric.'),
        def('For Count', 'Norms are percentages of the total traffic leaving the same source node. A norm of 50 % on A→B means “at most half of everything leaving A should go to B”.'),
        def('For time metrics', 'Norms are absolute values (seconds), compared directly against the edge’s Avg/Min/Max/Std-Dev time.'),
      ],
    },
    {
      heading: 'Setting and reading norms',
      body: [
        p('Click “Edit norms”, then click an edge and type its target. In view mode each edge turns green or red depending on whether the actual value meets the norm; the “Norm is a minimum” toggle flips the comparison so the actual must be ≥ the norm instead of ≤.'),
        p('“Show gaps” opens the full gap-analysis table — from, to, actual, norm, delta and status — sorted with violations first. The gap analysis is also appended to the AI Documentation report.'),
        tip('Norms round-trip through Backup & Restore, so a target model built once can be shared or moved between installations.'),
      ],
    },
  ],
}

// ── Happy Path ────────────────────────────────────────────────────────────────

const happyPath: HelpTopic = {
  id: 'happypath',
  title: 'Happy Path',
  subtitle: 'Define ideal step sequences and measure real conformance',
  icon: '🪧',
  sections: [
    {
      heading: 'Defining an ideal path',
      body: [
        p('A Happy Path is the ideal sequence a process should follow. Create one, then add trunk steps in order. You can add optional named branches — alternative continuations from the trunk — so a process with legitimate variations is scored fairly.'),
        p('The left panel shows the actual process map; the right panel is your ideal definition. Toggle Edit mode to add, reorder or remove steps.'),
      ],
    },
    {
      heading: 'The conformance score',
      body: [
        p('The score is a journey-count-weighted average of edge coverage: for each real journey variant, the fraction of the ideal path’s transitions that the variant actually contains, weighted by how many journeys followed it.'),
        ul(
          '1.00 — every journey follows the ideal path perfectly.',
          '0.00 — no journey shares a single transition with the ideal sequence.',
        ),
        p('When branches are defined, each journey is scored against whichever branch it matches best, so a case taking a legitimate alternative is not unfairly penalised.'),
        tip('Steps in your ideal path that are absent from the currently filtered process are shown dimmed, so you can immediately see which ideal steps never actually occur under the current filters.'),
      ],
    },
  ],
}

// ── Sampling ──────────────────────────────────────────────────────────────────

const sampling: HelpTopic = {
  id: 'sampling',
  title: 'Journey Sampling',
  subtitle: 'Representative subsets for fast, meaningful analysis',
  icon: '▤',
  sections: [
    {
      heading: 'Why sample?',
      body: [
        p('On very large event logs, working with a representative subset keeps exploration interactive while preserving the process’s shape. Create up to three named sample sets from the original data; the A and B chart slots can each select their own sample independently.'),
        p('Samples are written to a SAMPLE_SET column on the JOURNEYS table (added automatically on first use). The original rows are never modified, and deleting a sample removes only its rows.'),
      ],
    },
    {
      heading: 'The three strategies',
      body: [
        def('Random', 'Uniform random journey selection. The simplest baseline — fast and unbiased, but rare variants may be under-represented.'),
        def('Temporal Stratified', 'Proportional selection across equal calendar-month buckets, so the sample preserves the time distribution of the original — useful when volume varies seasonally.'),
        def('Path Diversity', 'Coverage-maximising selection across distinct journey variants, so rare paths are more likely to appear — useful when you care about the full variety of behaviour, not just the common cases.'),
      ],
    },
    {
      heading: 'Using samples & simulations as A/B sources',
      body: [
        p('In the Sampling section, each of the A and B slots has a picker that selects Original data, one of the three sample sets, or a stored Simulation result (Sim-A / Sim-B). This is how you feed simulated processes into A/B Comparison to compare them against real data — or against each other.'),
      ],
    },
  ],
}

// ── AI Documentation ──────────────────────────────────────────────────────────

const aiDocumentation: HelpTopic = {
  id: 'ai',
  title: 'AI supported Documentation',
  subtitle: 'AI-powered process analysis and a structured report',
  icon: '🧠',
  sections: [
    {
      heading: 'How it works',
      body: [
        p('The AI Documentation view sends the current A-Chart transition table, together with your prompt template, to the OpenAI-compatible endpoint configured on the active connection, and renders the answer as a structured Markdown report.'),
        p('The report also includes sections computed locally and never sent to the model: the journey-paths table, happy-path conformance, the conformance gap analysis, and your notes. Before running, notice cards summarise the A-Chart filter context plus how many happy paths and norms will be included.'),
        tip('Edit the prompt under Configuration → LLM Prompt; templates are stored per project. Use the browser’s Print / PDF to export the finished report.'),
      ],
    },
    {
      heading: 'Requirements',
      body: [
        ul(
          'The active connection must have an LLM server attached (base URL, model, optional API key).',
          'The second status dot on the connection card must be blue — the model server is reachable.',
          'Any OpenAI-compatible endpoint works: local servers (Ollama, llama.cpp, vLLM, LM Studio) or cloud APIs.',
        ),
        warn('AI models can produce results that are incorrect, incomplete or misleading. Independently verify every finding before acting on it.'),
      ],
    },
  ],
}

// ── Notes ─────────────────────────────────────────────────────────────────────

const notes: HelpTopic = {
  id: 'notes',
  title: 'Process Notes',
  subtitle: 'Annotate nodes and edges with sticky notes',
  icon: '🗒',
  sections: [
    {
      heading: 'Creating and finding notes',
      body: [
        p('Click a node or an edge and choose “Show Notes” to add an annotation. A yellow ✎ badge marks any node or edge that carries a note. The Notes view lists every note for the project — searchable, newest first — independent of the current filters.'),
        p('Each note records its author, who last edited it, and the complete filter context at the time it was created, so the observation stays interpretable later. Mark a note as “shared” to make it visible to other users of the same database.'),
      ],
    },
    {
      heading: 'Storage',
      body: [
        p('Notes are stored in a NOTES table in your Exasol database, created automatically on first use if the connecting user has CREATE TABLE permission. This means notes travel with the data and are visible to every user of that database (subject to the shared flag), not just on the machine that wrote them.'),
      ],
    },
  ],
}

// ── Backup & Restore ──────────────────────────────────────────────────────────

const backup: HelpTopic = {
  id: 'backup',
  title: 'Backup & Restore',
  subtitle: 'Export and import your settings and annotations',
  icon: '💾',
  sections: [
    {
      heading: 'What is included',
      body: [
        p('A backup exports everything except the event data itself: connections and servers, filter presets, happy paths, target norms, saved node layouts, LLM prompt templates and app preferences — as a single JSON file. Passwords and API keys are included only if you tick the corresponding boxes.'),
        tip('The format is interchangeable with the macOS version of the app, so a backup taken there restores here and vice-versa.'),
      ],
    },
    {
      heading: 'Encryption',
      body: [
        p('Set an encryption password to protect the file with AES-256-GCM (PBKDF2-HMAC-SHA256, 100 000 iterations, a random 16-byte salt and 12-byte nonce). Restore inspects the file first and shows a summary — connection count, projects, whether layouts/norms/happy-paths/presets are present — before you commit, and lets you choose exactly which categories to restore.'),
        warn('If you include passwords or API keys without setting an encryption password, they are written in plain text in the JSON file. Set a password whenever the backup contains secrets.'),
      ],
    },
  ],
}

// ── Configuration ─────────────────────────────────────────────────────────────

const configuration: HelpTopic = {
  id: 'configuration',
  title: 'Configuration',
  subtitle: 'Display options, KPIs, step colours, shapes, scores and groups',
  icon: '⚙️',
  sections: [
    {
      heading: 'Display options',
      body: [
        def('Show step groups', 'Toggles the dashed BELONGS_TO group boxes. When on, “Groups start” chooses whether groups load Expanded, Collapsed, or in their last Persisted state.'),
        def('Show node notes', 'Shows the shortened DESCRIPTION under the step name on each node, and the yellow note badges.'),
        def('Optimise layout', 'Enables barycenter crossing-minimisation for a cleaner arrangement on complex graphs.'),
        def('Colorise edges by weight', 'Turns on the per-metric colour scales (configure them from the map’s colour legend).'),
        def('Date slider', 'Switches the map’s date control between Range (two thumbs) and Day (single day) mode.'),
      ],
    },
    {
      heading: 'KPIs, steps and preferences',
      body: [
        p('The KPIs sub-section lets you drag to reorder the KPI tiles and toggle each one on or off. The Steps sub-section is the in-app Step Editor: pick a step, then set its background/foreground colour, shape, score, group and description — changes are written straight to the STEPS table and the map redraws.'),
        p('Backup & Restore and the LLM prompt template editor also live in this section. Theme (System / Light / Dark) is chosen from the bar at the bottom of the sidebar. (Sign-in is now managed centrally in the admin interface, so there is no per-client authentication toggle here.)'),
      ],
    },
  ],
}

// ── Troubleshooting ───────────────────────────────────────────────────────────

const troubleshooting: HelpTopic = {
  id: 'troubleshooting',
  title: 'Troubleshooting',
  subtitle: 'Common problems and their fixes',
  icon: '🛟',
  sections: [
    {
      heading: 'Common issues',
      body: [
        def('No connections listed', 'No connection has been assigned to your account. Ask an administrator to grant you one in the admin interface (Database Connections tab).'),
        def('Cannot connect to Exasol', 'Connection settings (host, port, credentials, TLS, RSA key size) are managed by an administrator. If a connection fails, ask them to check it with Test connection in the admin interface — for Exasol 7.x or the Docker image the minimum RSA key size must be 1024 bits, and the account needs SELECT on the required tables.'),
        def('Cannot sign in', 'Confirm your account is enabled (an administrator can check the Users tab). Directory (LDAP) accounts must exist in the directory and, for the admin interface, be tagged Admin locally.'),
        def('Statistics / goodness query times out', 'Narrow the date range or add filters — a 30-second limit applies. The affected tile shows “—”.'),
        def('Simulation returns no journeys', 'The graph needs at least one start step (in-degree / out-degree < 0.2); exclusions may have removed all entry points. Required steps that never occur also drop every journey.'),
        def('AI Documentation stays blank', 'Confirm the active connection has an LLM server attached and its status dot is blue (reachable); the LLM URL, model and API key are set by an administrator.'),
        def('Notes are not saved', 'The connecting user needs CREATE TABLE (first use) and INSERT / DELETE on NOTES.'),
        def('Sample cannot be created', 'The user needs ALTER TABLE and INSERT on JOURNEYS.'),
      ],
    },
  ],
}

export const HELP_TOPICS: HelpTopic[] = [
  overview,
  database,
  connecting,
  administration,
  chartViews,
  filters,
  filterPresets,
  processMap,
  kpi,
  processGoodness,
  processSimilarity,
  simulation,
  conformance,
  happyPath,
  sampling,
  aiDocumentation,
  notes,
  backup,
  configuration,
  troubleshooting,
]
