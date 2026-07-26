/** Notes list — port of `commentsContent` from ProcessMapView.swift. */

import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  ImportanceBadge,
  NoteEditorSheet,
  snapshotSummary,
  type NoteEditorTarget,
} from '../components/NoteEditor'
import { KpiTile } from '../components/KpiStrip'
import { Unavailable } from '../components/ui'
import { formatDateTime } from '../graph/format'
import { useStore } from '../store'
import {
  NOTE_IMPORTANCE_LEVELS,
  NOTE_IMPORTANCE_META,
  noteTargetLabel,
  normalizeImportance,
  type NoteImportance,
} from '../types'

type TimeWindow = 'ALL' | '7' | '30' | '90'
const TIME_LABELS: Record<TimeWindow, string> = {
  ALL: 'Any time',
  '7': 'Last 7 days',
  '30': 'Last 30 days',
  '90': 'Last 90 days',
}

// Least → highest importance (drives KPI order left→right and group order).
const IMPORTANCE_RANK: Record<NoteImportance, number> = {
  NORMAL: 0,
  INFO: 1,
  IMPORTANT: 2,
  URGENT: 3,
}

export function NotesView() {
  const store = useStore()
  const [editing, setEditing] = useState<NoteEditorTarget | null>(null)
  const [search, setSearch] = useState('')
  const [importance, setImportance] = useState<'ALL' | NoteImportance>('ALL')
  const [author, setAuthor] = useState<string>('ALL')
  const [time, setTime] = useState<TimeWindow>('ALL')
  const [status, setStatus] = useState<'ALL' | 'OPEN' | 'RESOLVED'>('ALL')
  const [sortDir, setSortDir] = useState<'newest' | 'oldest'>('newest')
  const [grouped, setGrouped] = useState(false)
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(0)

  // Distinct note authors (by stable login username), labelled with the real name.
  const authors = useMemo(() => {
    const byUser = new Map<string, string>()
    for (const n of store.projectNotes) {
      const key = n.username ?? ''
      if (!byUser.has(key)) byUser.set(key, n.authorName || n.username || '—')
    }
    return [...byUser.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [store.projectNotes])

  // Notes filtered by everything EXCEPT importance, plus the per-importance counts
  // (so the KPI strip always shows the full breakdown of the current context).
  const { base, counts, resolvedCount } = useMemo(() => {
    const term = search.trim().toLowerCase()
    const cutoff = time === 'ALL' ? null : Date.now() - Number(time) * 86_400_000
    const base = store.projectNotes.filter((n) => {
      if (
        term &&
        !n.text.toLowerCase().includes(term) &&
        !(n.title ?? '').toLowerCase().includes(term) &&
        !noteTargetLabel(n.target).toLowerCase().includes(term)
      )
        return false
      if (author !== 'ALL' && (n.username ?? '') !== author) return false
      if (status === 'OPEN' && n.resolved) return false
      if (status === 'RESOLVED' && !n.resolved) return false
      if (cutoff !== null && new Date(n.createdAt).getTime() < cutoff) return false
      return true
    })
    const counts: Record<NoteImportance, number> = {
      NORMAL: 0,
      INFO: 0,
      IMPORTANT: 0,
      URGENT: 0,
    }
    let resolvedCount = 0
    for (const n of base) {
      counts[normalizeImportance(n.importance)]++
      if (n.resolved) resolvedCount++
    }
    return { base, counts, resolvedCount }
  }, [store.projectNotes, search, author, time, status])

  const notes = useMemo(() => {
    const filtered =
      importance === 'ALL'
        ? base
        : base.filter((n) => normalizeImportance(n.importance) === importance)
    return [...filtered].sort((a, b) => {
      if (grouped) {
        const r =
          IMPORTANCE_RANK[normalizeImportance(b.importance)] -
          IMPORTANCE_RANK[normalizeImportance(a.importance)] // highest group first
        if (r !== 0) return r
      }
      const byDate = b.createdAt.localeCompare(a.createdAt) // newest first
      return sortDir === 'newest' ? byDate : -byDate
    })
  }, [base, importance, grouped, sortDir])

  // Any filter/sort/group change or a resized page resets to the first page.
  useEffect(
    () => setPage(0),
    [search, importance, author, time, status, sortDir, grouped, pageSize],
  )

  if (store.projectNotes.length === 0) {
    return (
      <Unavailable
        glyph="🗒"
        title="No Notes"
        description="Click a node or an edge on the process map and choose “Show Notes” to add one."
      />
    )
  }

  const selectStyle: React.CSSProperties = { padding: '4px 8px', fontSize: 13 }

  const pageCount = Math.max(1, Math.ceil(notes.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const pageNotes = notes.slice(safePage * pageSize, safePage * pageSize + pageSize)
  const firstShown = notes.length === 0 ? 0 : safePage * pageSize + 1
  const lastShown = Math.min(notes.length, (safePage + 1) * pageSize)

  return (
    <div className="col" style={{ flex: 1, minHeight: 0, gap: 0 }}>
      {/* Total, one KPI per importance (least→highest, coloured like the badges),
          then Resolved. */}
      <div className="kpi-strip">
        <KpiTile label="Total Notes" icon="🗒" value={base.length.toLocaleString()} />
        {NOTE_IMPORTANCE_LEVELS.map((lvl) => {
          const m = NOTE_IMPORTANCE_META[lvl]
          return (
            <KpiTile
              key={lvl}
              label={m.label}
              icon={m.glyph}
              value={counts[lvl].toLocaleString()}
              color={m.color}
            />
          )
        })}
        <KpiTile
          label="Resolved"
          icon="✓"
          value={resolvedCount.toLocaleString()}
          color="var(--green)"
        />
      </div>

      <div
        className="row"
        style={{
          padding: '8px 16px',
          gap: 10,
          flexWrap: 'wrap',
          alignItems: 'center',
          background: 'var(--bg-tertiary-grouped)',
          borderBottom: '1px solid var(--separator-soft)',
        }}
      >
        <div className="search-row" style={{ flex: '1 1 200px', maxWidth: 300 }}>
          <span aria-hidden className="fg-secondary">
            🔍
          </span>
          <input
            value={search}
            placeholder="Filter notes"
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button className="fg-secondary" onClick={() => setSearch('')}>
              ⊗
            </button>
          )}
        </div>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Importance
          <select
            className="text-input"
            style={selectStyle}
            value={importance}
            onChange={(e) => setImportance(e.target.value as 'ALL' | NoteImportance)}
          >
            <option value="ALL">All</option>
            {NOTE_IMPORTANCE_LEVELS.map((lvl) => (
              <option key={lvl} value={lvl}>
                {NOTE_IMPORTANCE_META[lvl].label}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          User
          <select
            className="text-input"
            style={selectStyle}
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
          >
            <option value="ALL">All</option>
            {authors.map(([user, label]) => (
              <option key={user} value={user}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Time
          <select
            className="text-input"
            style={selectStyle}
            value={time}
            onChange={(e) => setTime(e.target.value as TimeWindow)}
          >
            {(Object.keys(TIME_LABELS) as TimeWindow[]).map((w) => (
              <option key={w} value={w}>
                {TIME_LABELS[w]}
              </option>
            ))}
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Status
          <select
            className="text-input"
            style={selectStyle}
            value={status}
            onChange={(e) => setStatus(e.target.value as 'ALL' | 'OPEN' | 'RESOLVED')}
          >
            <option value="ALL">All</option>
            <option value="OPEN">Unresolved</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Sort
          <select
            className="text-input"
            style={selectStyle}
            value={sortDir}
            onChange={(e) => setSortDir(e.target.value as 'newest' | 'oldest')}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 6 }}>
          <input
            type="checkbox"
            checked={grouped}
            onChange={(e) => setGrouped(e.target.checked)}
          />
          Group by importance
        </label>

        <label className="row t-caption fg-secondary" style={{ gap: 4 }}>
          Per page
          <select
            className="text-input"
            style={selectStyle}
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            {[5, 10, 20].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <span className="t-caption fg-secondary">
          {notes.length} of {store.projectNotes.length}
        </span>
        <span className="spacer" />
        <button className="btn small" onClick={() => void store.loadNotes()}>
          ↻ Reload
        </button>
      </div>

      <div className="scroll-view">
        {notes.length === 0 && (
          <div
            className="t-caption fg-secondary"
            style={{ padding: '16px', textAlign: 'center' }}
          >
            No notes match the current filters.
          </div>
        )}
        {pageNotes.map((note, i) => {
          const imp = normalizeImportance(note.importance)
          const showHeader =
            grouped &&
            (i === 0 || normalizeImportance(pageNotes[i - 1].importance) !== imp)
          return (
            <Fragment key={note.id}>
              {showHeader && (
                <div
                  className="note-group-header"
                  style={{ color: NOTE_IMPORTANCE_META[imp].color }}
                >
                  {NOTE_IMPORTANCE_META[imp].glyph} {NOTE_IMPORTANCE_META[imp].label} (
                  {counts[imp]})
                </div>
              )}
              <button
                className="note-card"
                style={{ textAlign: 'left', cursor: 'pointer' }}
                onClick={() =>
                  setEditing({
                    target: note.target,
                    existing: note,
                    snapshot: note.filterSnapshot,
                  })
                }
              >
                <div className="n-head">
                  <span aria-hidden>{note.target.type === 'edge' ? '↝' : '⬭'}</span>
                  <strong>{noteTargetLabel(note.target)}</strong>
                  <ImportanceBadge level={imp} />
                  {note.resolved && (
                    <span
                      title="Resolved"
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 3,
                        padding: '1px 7px',
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--green)',
                        background: 'rgba(48,209,88,0.16)',
                      }}
                    >
                      ✓ Resolved
                    </span>
                  )}
                  <span className="spacer" />
                  {note.isShared && <span title="Shared with other users">👥</span>}
                  <span>{note.authorName || note.username || '—'}</span>
                  <span>{formatDateTime(note.createdAt)}</span>
                </div>
                <div className="n-title">{note.title || '—'}</div>
                <div className="n-text">{note.text}</div>
                <div className="n-meta">{snapshotSummary(note.filterSnapshot)}</div>
              </button>
            </Fragment>
          )
        })}
      </div>

      {notes.length > 0 && (
        <div
          className="row"
          style={{
            padding: '8px 16px',
            gap: 10,
            alignItems: 'center',
            background: 'var(--bg-tertiary-grouped)',
            borderTop: '1px solid var(--separator-soft)',
          }}
        >
          <button
            className="btn small"
            disabled={safePage === 0}
            onClick={() => setPage(safePage - 1)}
          >
            ‹ Prev
          </button>
          <span className="t-caption fg-secondary">
            Page {safePage + 1} of {pageCount}
          </span>
          <button
            className="btn small"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
          >
            Next ›
          </button>
          <span className="spacer" />
          <span className="t-caption fg-secondary">
            {firstShown}–{lastShown} of {notes.length}
          </span>
        </div>
      )}

      {editing && <NoteEditorSheet item={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
