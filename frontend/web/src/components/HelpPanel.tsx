/** Floating, draggable, resizable help panel — port of HelpView.swift +
 *  `FloatingHelpPanel` from ContentView.swift.
 *
 *  Content lives in `../help/content.ts` as structured blocks (paragraph / tip /
 *  warning / bullets / definition / code), rendered here with the same visual
 *  treatment as the macOS app. Printing the panel produces the full paginated
 *  document that the Swift app exported as a PDF. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { HELP_TOPICS, type HelpBlock, type HelpTopic } from '../help/content'
import { Logo } from './Logo'

function Block({ block }: { block: HelpBlock }) {
  switch (block.kind) {
    case 'paragraph':
      return <p className="help-p">{block.text}</p>
    case 'tip':
      return (
        <div className="help-callout tip">
          <span className="help-callout-icon" aria-hidden>
            💡
          </span>
          <span>{block.text}</span>
        </div>
      )
    case 'warning':
      return (
        <div className="help-callout warning">
          <span className="help-callout-icon" aria-hidden>
            ⚠️
          </span>
          <span>{block.text}</span>
        </div>
      )
    case 'bullets':
      return (
        <ul className="help-bullets">
          {block.items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )
    case 'definition':
      return (
        <div className="help-def">
          <span className="help-def-term">{block.term}</span>
          <span className="help-def-detail">{block.detail}</span>
        </div>
      )
    case 'code':
      return (
        <pre className="help-code">
          <code>{block.text}</code>
        </pre>
      )
  }
}

function TopicView({ topic }: { topic: HelpTopic }) {
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
        <section key={i} className="help-section">
          <h2 className="help-heading">{section.heading}</h2>
          {section.body.map((block, j) => (
            <Block key={j} block={block} />
          ))}
        </section>
      ))}
    </article>
  )
}

export function HelpPanel({ onClose }: { onClose: () => void }) {
  const [topicId, setTopicId] = useState(HELP_TOPICS[0].id)
  const [pos, setPos] = useState({ x: window.innerWidth * 0.42, y: 80 })
  const [size, setSize] = useState({ width: 760, height: 640 })
  const [printAll, setPrintAll] = useState(false)
  const drag = useRef<{ mode: 'move' | 'resize'; x: number; y: number } | null>(null)

  const topic = useMemo(
    () => HELP_TOPICS.find((t) => t.id === topicId) ?? HELP_TOPICS[0],
    [topicId],
  )

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
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Print the entire documentation (all chapters) rather than just the panel.
  const printDocumentation = useCallback(() => {
    setPrintAll(true)
    window.requestAnimationFrame(() => {
      window.print()
      // Reset after the print dialog returns.
      window.setTimeout(() => setPrintAll(false), 500)
    })
  }, [])

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
            {HELP_TOPICS.map((t) => (
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
            ))}
          </nav>

          <div className="help-content">
            <TopicView topic={topic} />
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
