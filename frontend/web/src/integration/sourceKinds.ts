/** The generic registry of source *kinds* the "Add source" wizard is built from.
 *
 *  Each kind declares its config fields; the wizard renders the right form from the
 *  descriptor, and the backend stores `{kind, config}` opaquely — so adding a new kind
 *  (a database, a REST API, object storage, …) is a matter of adding an entry here (and
 *  allowing the kind id in `SOURCE_KINDS` on the backend). Only "file" is available for
 *  now; the rest are listed as `available: false` to show the intended structure. */

// 'sourceType' is a dynamic picker of the user's source types (stored as an id in the
// config); the wizard populates its options at runtime.
export type SourceFieldType = 'text' | 'password' | 'number' | 'select' | 'sourceType'

export interface SourceFieldDef {
  key: string
  label: string
  type: SourceFieldType
  placeholder?: string
  help?: string
  required?: boolean
  options?: string[] // for `select`
  default?: string
  // Row layout hint: 'full' = own row (default), 'grow' = share a row & take the
  // slack, 'narrow' = share a row at a fixed width (e.g. an encoding select).
  layout?: 'full' | 'grow' | 'narrow'
}

export interface SourceKindDef {
  id: string
  label: string
  icon: string
  description: string
  available: boolean
  fields: SourceFieldDef[]
  /** One-line summary of a saved source's config, shown on its badge. */
  summary: (config: Record<string, unknown>) => string
}

export const SOURCE_KINDS: SourceKindDef[] = [
  {
    id: 'file',
    label: 'File',
    icon: '📄',
    description: 'A log or data file the extractor reads at run time.',
    available: true,
    fields: [
      {
        key: 'path',
        label: 'File path or glob',
        type: 'text',
        placeholder: '/var/log/app/access.log  or  /data/logs/*.log',
        help: 'Path (or glob) the extractor reads when the source runs.',
        required: true,
        layout: 'grow',
      },
      {
        key: 'encoding',
        label: 'Encoding',
        type: 'select',
        options: ['utf-8', 'latin-1', 'utf-16'],
        default: 'utf-8',
        layout: 'narrow',
      },
      {
        key: 'sourceTypeId',
        label: 'Source type',
        type: 'sourceType',
        help: 'The parser applied to each line when this source runs.',
      },
    ],
    summary: (c) => String(c.path ?? '(no path)'),
  },
  // ── Future kinds — structure only, not selectable yet ──────────────────────
  {
    id: 'database',
    label: 'Database',
    icon: '🗄️',
    description: 'Rows from a database table or query.',
    available: false,
    fields: [
      { key: 'dsn', label: 'Connection string', type: 'text', required: true },
      { key: 'query', label: 'Table or SQL query', type: 'text', required: true },
    ],
    summary: (c) => String(c.query ?? c.dsn ?? ''),
  },
  {
    id: 'rest',
    label: 'REST API',
    icon: '🌐',
    description: 'Records fetched from an HTTP endpoint.',
    available: false,
    fields: [
      { key: 'url', label: 'Endpoint URL', type: 'text', required: true },
      { key: 'token', label: 'Bearer token', type: 'password' },
    ],
    summary: (c) => String(c.url ?? ''),
  },
  {
    id: 'object-storage',
    label: 'Object storage',
    icon: '☁️',
    description: 'Objects from an S3-compatible bucket.',
    available: false,
    fields: [
      { key: 'bucket', label: 'Bucket', type: 'text', required: true },
      { key: 'prefix', label: 'Prefix', type: 'text' },
    ],
    summary: (c) => `${c.bucket ?? ''}${c.prefix ? '/' + c.prefix : ''}`,
  },
]

export const sourceKind = (id: string): SourceKindDef | undefined =>
  SOURCE_KINDS.find((k) => k.id === id)
