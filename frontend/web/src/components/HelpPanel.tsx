/** Floating, draggable, resizable help panel — port of HelpView.swift +
 *  `FloatingHelpPanel` from ContentView.swift.
 *
 *  Content lives in `../help/content.ts` as structured blocks (paragraph / tip /
 *  warning / bullets / definition / code), rendered here with the same visual
 *  treatment as the macOS app. Printing the panel produces the full paginated
 *  document that the Swift app exported as a PDF. A search box filters the table
 *  of contents to matching sections and highlights hits in the rendered chapter. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { HELP_TOPICS, type HelpBlock, type HelpTopic } from '../help/content'
import { Logo } from './Logo'

/** Table-of-contents sub-groups: the listed chapters are nested under one
 *  collapsible heading instead of sitting flat in the nav. */
const HELP_GROUPS: { label: string; icon: string; topicIds: string[] }[] = [
  {
    label: 'Computational Insights',
    icon: '🧮',
    topicIds: ['processgoodness', 'processsimilarity'],
  },
]

type NavNode =
  | { kind: 'topic'; topic: HelpTopic }
  | { kind: 'group'; label: string; icon: string; topics: HelpTopic[] }

/** Fold the grouped chapters into a single group node (placed where the first
 *  member sits) while leaving every other chapter flat and in order. */
function buildNav(topics: HelpTopic[]): NavNode[] {
  const groupOf = new Map<string, (typeof HELP_GROUPS)[number]>()
  for (const g of HELP_GROUPS) for (const id of g.topicIds) groupOf.set(id, g)

  const nodes: NavNode[] = []
  const emitted = new Set<string>()
  for (const topic of topics) {
    const group = groupOf.get(topic.id)
    if (!group) {
      nodes.push({ kind: 'topic', topic })
      continue
    }
    if (emitted.has(group.label)) continue
    emitted.add(group.label)
    nodes.push({
      kind: 'group',
      label: group.label,
      icon: group.icon,
      topics: topics.filter((t) => groupOf.get(t.id)?.label === group.label),
    })
  }
  return nodes
}

/** All searchable text in a block, flattened to one string. */
function blockText(block: HelpBlock): string {
  switch (block.kind) {
    case 'paragraph':
    case 'tip':
    case 'warning':
    case 'code':
      return block.text
    case 'bullets':
      return block.items.join(' ')
    case 'definition':
      return `${block.term} ${block.detail}`
  }
}

/** Wrap every case-insensitive occurrence of `query` in `text` with <mark>. */
function Highlight({ text, query }: { text: string; query: string }) {
  const q = query.trim()
  if (!q) return <>{text}</>
  const parts: React.ReactNode[] = []
  const lower = text.toLowerCase()
  const ql = q.toLowerCase()
  let i = 0
  let key = 0
  let idx = lower.indexOf(ql)
  while (idx !== -1) {
    if (idx > i) parts.push(text.slice(i, idx))
    parts.push(
      <mark key={key++} className="help-mark">
        {text.slice(idx, idx + q.length)}
      </mark>,
    )
    i = idx + q.length
    idx = lower.indexOf(ql, i)
  }
  parts.push(text.slice(i))
  return <>{parts}</>
}

function Block({ block, query }: { block: HelpBlock; query: string }) {
  switch (block.kind) {
    case 'paragraph':
      return (
        <p className="help-p">
          <Highlight text={block.text} query={query} />
        </p>
      )
    case 'tip':
      return (
        <div className="help-callout tip">
          <span className="help-callout-icon" aria-hidden>
            💡
          </span>
          <span>
            <Highlight text={block.text} query={query} />
          </span>
        </div>
      )
    case 'warning':
      return (
        <div className="help-callout warning">
          <span className="help-callout-icon" aria-hidden>
            ⚠️
          </span>
          <span>
            <Highlight text={block.text} query={query} />
          </span>
        </div>
      )
    case 'bullets':
      return (
        <ul className="help-bullets">
          {block.items.map((item, i) => (
            <li key={i}>
              <Highlight text={item} query={query} />
            </li>
          ))}
        </ul>
      )
    case 'definition':
      return (
        <div className="help-def">
          <span className="help-def-term">
            <Highlight text={block.term} query={query} />
          </span>
          <span className="help-def-detail">
            <Highlight text={block.detail} query={query} />
          </span>
        </div>
      )
    case 'code':
      return (
        <pre className="help-code">
          <code>
            <Highlight text={block.text} query={query} />
          </code>
        </pre>
      )
  }
}

function TopicView({
  topic,
  query = '',
  anchors = false,
}: {
  topic: HelpTopic
  query?: string
  anchors?: boolean
}) {
  return (
    <article>
      <header className="help-topic-head">
        <span className="help-topic-icon" aria-hidden>
          {topic.icon}
        </span>
        <div>
          <h1 className="help-topic-title">{topic.title}</h1>
          <p className="help-topic-subtitle">{topic.subtitle}</p>
        </div>
      </header>
      {topic.sections.map((section, i) => (
        <section
          key={i}
          id={anchors ? `help-sec-${i}` : undefined}
          className="help-section"
        >
          <h2 className="help-heading">
            <Highlight text={section.heading} query={query} />
          </h2>
          {section.body.map((block, j) => (
            <Block key={j} block={block} query={query} />
          ))}
        </section>
      ))}
    </article>
  )
}

interface SearchResult {
  topicId: string
  icon: string
  heading: string
  sectionIndex: number
  snippet: string
}

/** A short context window around the first match, for the result list. */
function snippetOf(text: string, query: string): string {
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text.slice(0, 80)
  const start = Math.max(0, idx - 30)
  const end = Math.min(text.length, idx + query.length + 50)
  return (start > 0 ? '…' : '') + text.slice(start, end).trim() + (end < text.length ? '…' : '')
}

export function HelpPanel({ onClose }: { onClose: () => void }) {
  const [topicId, setTopicId] = useState(HELP_TOPICS[0].id)
  const [query, setQuery] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [pos, setPos] = useState({ x: window.innerWidth * 0.42, y: 80 })
  const [size, setSize] = useState({ width: 760, height: 640 })
  const [printAll, setPrintAll] = useState(false)
  const drag = useRef<{ mode: 'move' | 'resize'; x: number; y: number } | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  // A search hit to scroll to once its chapter renders. A ref (not state) so
  // clearing it doesn't re-run the scroll effect and reset the scroll position.
  const pendingSection = useRef<number | null>(null)

  const topic = useMemo(
    () => HELP_TOPICS.find((t) => t.id === topicId) ?? HELP_TOPICS[0],
    [topicId],
  )

  // Match every section whose heading or body text contains the query.
  const results = useMemo<SearchResult[]>(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const out: SearchResult[] = []
    for (const t of HELP_TOPICS) {
      t.sections.forEach((section, idx) => {
        const hay = [section.heading, ...section.body.map(blockText)].join('  ')
        if (hay.toLowerCase().includes(q)) {
          out.push({
            topicId: t.id,
            icon: t.icon,
            heading: section.heading,
            sectionIndex: idx,
            snippet: snippetOf(hay, query.trim()),
          })
        }
      })
    }
    return out
  }, [query])

  const scrollToSection = useCallback((index: number) => {
    contentRef.current
      ?.querySelector(`#help-sec-${index}`)
      ?.scrollIntoView?.({ block: 'start' })
  }, [])

  const openResult = useCallback(
    (r: SearchResult) => {
      if (r.topicId === topicId) {
        scrollToSection(r.sectionIndex) // same chapter — jump straight there
      } else {
        pendingSection.current = r.sectionIndex // scroll after the chapter renders
        setTopicId(r.topicId)
      }
    },
    [topicId, scrollToSection],
  )

  // When the chapter changes: scroll to a pending search hit, else reset to top.
  useEffect(() => {
    const c = contentRef.current
    if (!c) return
    if (pendingSection.current != null) {
      scrollToSection(pendingSection.current)
      pendingSection.current = null
    } else {
      c.scrollTop = 0
    }
  }, [topicId, scrollToSection])

  const onPointerMove = useCallback((event: PointerEvent) => {
    const state = drag.current
    if (!state) return
    const dx = event.clientX - state.x
    const dy = event.clientY - state.y
    drag.current = { ...state, x: event.clientX, y: event.clientY }
    if (state.mode === 'move') {
      setPos((prev) => ({
        x: Math.max(0, Math.min(window.innerWidth - 220, prev.x + dx)),
        y: Math.max(0, Math.min(window.innerHeight - 60, prev.y + dy)),
      }))
    } else {
      setSize((prev) => ({
        width: Math.max(420, prev.width + dx),
        height: Math.max(320, prev.height + dy),
      }))
    }
  }, [])

  useEffect(() => {
    const stop = () => {
      drag.current = null
    }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', stop)
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', stop)
    }
  }, [onPointerMove])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Escape clears an active search first, then closes the panel.
      if (e.key === 'Escape') {
        if (query) setQuery('')
        else onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, query])

  // Print the entire documentation (all chapters) rather than just the panel.
  const printDocumentation = useCallback(() => {
    setPrintAll(true)
    window.requestAnimationFrame(() => {
      window.print()
      // Reset after the print dialog returns.
      window.setTimeout(() => setPrintAll(false), 500)
    })
  }, [])

  const searching = query.trim().length > 0

  return (
    <>
      <div
        className={`help-panel${printAll ? ' printing' : ''}`}
        style={{ left: pos.x, top: pos.y, width: size.width, height: size.height }}
        role="dialog"
        aria-label="Help"
      >
        <div
          className="help-title-bar"
          onPointerDown={(e) => {
            drag.current = { mode: 'move', x: e.clientX, y: e.clientY }
          }}
        >
          <span aria-hidden className="fg-accent">
            ？
          </span>
          <span className="t-headline spacer">Help — {topic.title}</span>
          <button
            className="icon-btn"
            title="Print / export the full documentation as PDF"
            onClick={printDocumentation}
          >
            ⎙
          </button>
          <button className="icon-btn" onClick={onClose} title="Close help">
            ✕
          </button>
        </div>

        <div className="help-body">
          <nav className="help-toc">
            <div className="help-search">
              <span aria-hidden className="help-search-icon">
                🔍
              </span>
              <input
                type="search"
                className="help-search-input"
                placeholder="Search help…"
                value={query}
                autoComplete="off"
                spellCheck={false}
                aria-label="Search help"
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && results.length > 0) openResult(results[0])
                }}
              />
              {query && (
                <button
                  className="help-search-clear"
                  title="Clear search"
                  aria-label="Clear search"
                  onClick={() => setQuery('')}
                >
                  ✕
                </button>
              )}
            </div>

            {searching ? (
              results.length > 0 ? (
                <>
                  <div className="help-search-count">
                    {results.length} {results.length === 1 ? 'result' : 'results'}
                  </div>
                  {results.map((r) => (
                    <button
                      key={`${r.topicId}-${r.sectionIndex}`}
                      className="help-search-result"
                      onClick={() => openResult(r)}
                    >
                      <span className="help-search-result-head">
                        <span aria-hidden style={{ width: 16, display: 'inline-block' }}>
                          {r.icon}
                        </span>
                        {r.heading}
                      </span>
                      <span className="help-search-result-snippet">
                        <Highlight text={r.snippet} query={query} />
                      </span>
                    </button>
                  ))}
                </>
              ) : (
                <p className="help-search-empty">No matches for “{query.trim()}”.</p>
              )
            ) : (
              buildNav(HELP_TOPICS).map((node) => {
                if (node.kind === 'topic') {
                  const t = node.topic
                  return (
                    <button
                      key={t.id}
                      className={t.id === topicId ? 'active' : ''}
                      onClick={() => setTopicId(t.id)}
                    >
                      <span aria-hidden style={{ width: 18, display: 'inline-block' }}>
                        {t.icon}
                      </span>
                      {t.title}
                    </button>
                  )
                }
                // Keep the group open while one of its chapters is the active one.
                const open =
                  !collapsedGroups.has(node.label) ||
                  node.topics.some((t) => t.id === topicId)
                return (
                  <div key={node.label} className="help-toc-group">
                    <button
                      className="help-toc-group-head"
                      aria-expanded={open}
                      onClick={() =>
                        setCollapsedGroups((prev) => {
                          const next = new Set(prev)
                          if (next.has(node.label)) next.delete(node.label)
                          else next.add(node.label)
                          return next
                        })
                      }
                    >
                      <span aria-hidden style={{ width: 18, display: 'inline-block' }}>
                        {node.icon}
                      </span>
                      <span className="spacer">{node.label}</span>
                      <span aria-hidden style={{ fontSize: 10 }}>
                        {open ? '▾' : '▸'}
                      </span>
                    </button>
                    {open &&
                      node.topics.map((t) => (
                        <button
                          key={t.id}
                          className={`help-toc-sub${t.id === topicId ? ' active' : ''}`}
                          onClick={() => setTopicId(t.id)}
                        >
                          <span
                            aria-hidden
                            style={{ width: 18, display: 'inline-block' }}
                          >
                            {t.icon}
                          </span>
                          {t.title}
                        </button>
                      ))}
                  </div>
                )
              })
            )}
          </nav>

          <div className="help-content" ref={contentRef}>
            <TopicView topic={topic} query={query} anchors />
          </div>
        </div>

        <div
          className="help-resize"
          onPointerDown={(e) => {
            drag.current = { mode: 'resize', x: e.clientX, y: e.clientY }
          }}
          title="Resize"
        >
          ⤡
        </div>
      </div>

      {/* Full documentation, portalled to <body> as a sibling of #root so the
          print stylesheet can hide the app and show only this. */}
      {printAll &&
        createPortal(
          <div className="help-print-doc">
            <div className="help-print-cover">
              <div className="help-print-logo" aria-hidden>
                <Logo />
              </div>
              <h1>Process Mining Demonstrator</h1>
              <p>User Documentation · Web Edition</p>
            </div>
            {HELP_TOPICS.map((t) => (
              <div key={t.id} className="help-print-chapter">
                <TopicView topic={t} />
              </div>
            ))}
          </div>,
          document.body,
        )}
    </>
  )
}
