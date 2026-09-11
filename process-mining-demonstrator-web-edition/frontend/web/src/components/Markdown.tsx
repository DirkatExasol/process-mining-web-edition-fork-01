/** Lightweight Markdown renderer — port of MarkdownView.swift.
 *
 * Supports the subset the app actually emits: headings, bold/italic/code spans,
 * fenced code, bullet and ordered lists, blockquotes, horizontal rules, pipe
 * tables, and raw `<table>` / `<div>` blocks that the report builder passes
 * through verbatim.
 */

import DOMPurify from 'dompurify'
import { useMemo, type ReactNode } from 'react'

const RAW_BLOCK = /^\s*<(table|div|hr|h[1-6])[\s>]/i

/** Allow only benign link schemes — a Markdown link can carry `javascript:` /
 *  `data:` URLs, and React does NOT strip those from an `href`, so an anchor
 *  built from note text or LLM output would be a script sink. Permit http(s),
 *  mailto and relative/anchor targets; neutralise everything else to `#`. */
function safeHref(url: string): string {
  const trimmed = url.trim()
  // Protocol-relative ("//host", or "/\host" which browsers normalise to "//host")
  // navigates off-site with no scheme — reject it before the relative check below.
  if (/^\/[/\\]/.test(trimmed)) return '#'
  // Relative, root-relative or in-page anchors carry no scheme — always safe.
  if (/^(\/|#|\.\/|\.\.\/)/.test(trimmed)) return trimmed
  if (/^(https?:|mailto:)/i.test(trimmed)) return trimmed
  // A token before ':' that isn't an allowed scheme (javascript:, data:, vbscript:…)
  // — or any control character used to smuggle one — is rejected.
  return '#'
}

/** Escapes text, then re-applies inline `**bold**`, `*italic*`, `` `code` ``. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let i = 0

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index))
    const token = match[0]
    const key = `${keyPrefix}-${i++}`
    if (token.startsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>)
    } else if (token.startsWith('[')) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token)
      nodes.push(
        linkMatch ? (
          <a key={key} href={safeHref(linkMatch[2])} rel="noopener noreferrer nofollow">
            {linkMatch[1]}
          </a>
        ) : (
          token
        ),
      )
    } else {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>)
    }
    lastIndex = match.index + token.length
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function splitRow(line: string): string[] {
  return line
    .replace(/^\s*\|/, '')
    .replace(/\|\s*$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

function isSeparatorRow(line: string): boolean {
  return /^\s*\|?[\s:-]*-[-\s:|]*\|?\s*$/.test(line) && line.includes('-')
}

function render(markdown: string): ReactNode[] {
  const lines = markdown.split('\n')
  const out: ReactNode[] = []
  let i = 0
  let key = 0

  const push = (node: ReactNode) => out.push(<div key={`b${key++}`}>{node}</div>)

  while (i < lines.length) {
    const line = lines[i]

    // Raw HTML block (report title page, TOC, journey-path table).
    if (RAW_BLOCK.test(line)) {
      const buffer: string[] = []
      // A raw block runs until a blank line at nesting level zero.
      while (i < lines.length && lines[i].trim() !== '') {
        buffer.push(lines[i])
        i++
      }
      out.push(
        <div
          key={`raw${key++}`}
          // Report HTML can originate from an LLM (via AI documentation), so treat
          // it as untrusted and sanitize before injecting — strips scripts, event
          // handlers and javascript: URLs while keeping the formatting tags.
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(buffer.join('\n')) }}
        />,
      )
      continue
    }

    // Fenced code
    if (line.trimStart().startsWith('```')) {
      const buffer: string[] = []
      i++
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
        buffer.push(lines[i])
        i++
      }
      i++
      out.push(
        <pre key={`code${key++}`}>
          <code>{buffer.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // Pipe table
    if (line.includes('|') && i + 1 < lines.length && isSeparatorRow(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(splitRow(lines[i]))
        i++
      }
      out.push(
        <table key={`table${key++}`}>
          <thead>
            <tr>
              {header.map((cell, ci) => (
                <th key={ci}>{inline(cell, `th${ci}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci}>{inline(cell, `td${ri}-${ci}`)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>,
      )
      continue
    }

    // Headings
    const heading = /^(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const content = inline(heading[2], `h${key}`)
      const Tag = `h${Math.min(level, 6)}` as 'h1'
      out.push(<Tag key={`h${key++}`}>{content}</Tag>)
      i++
      continue
    }

    // Horizontal rule
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      out.push(<hr key={`hr${key++}`} />)
      i++
      continue
    }

    // Blockquote
    if (line.trimStart().startsWith('>')) {
      const buffer: string[] = []
      while (i < lines.length && lines[i].trimStart().startsWith('>')) {
        buffer.push(lines[i].replace(/^\s*>\s?/, ''))
        i++
      }
      out.push(
        <blockquote key={`bq${key++}`}>{inline(buffer.join(' '), `bq${key}`)}</blockquote>,
      )
      continue
    }

    // Lists
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line)
    const ordered = /^\s*\d+\.\s+(.*)$/.exec(line)
    if (bullet || ordered) {
      const isOrdered = !!ordered
      const items: string[] = []
      while (i < lines.length) {
        const m = isOrdered
          ? /^\s*\d+\.\s+(.*)$/.exec(lines[i])
          : /^\s*[-*+]\s+(.*)$/.exec(lines[i])
        if (!m) break
        items.push(m[1])
        i++
      }
      const List = isOrdered ? 'ol' : 'ul'
      out.push(
        <List key={`list${key++}`}>
          {items.map((item, index) => (
            <li key={index}>{inline(item, `li${index}`)}</li>
          ))}
        </List>,
      )
      continue
    }

    // Paragraph
    if (line.trim() === '') {
      i++
      continue
    }
    const buffer: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,6}\s|```|\s*[-*+]\s|\s*\d+\.\s|\s*>)/.test(lines[i]) &&
      !RAW_BLOCK.test(lines[i])
    ) {
      buffer.push(lines[i])
      i++
    }
    if (buffer.length > 0) {
      push(<p>{inline(buffer.join(' '), `p${key}`)}</p>)
    }
  }

  return out
}

export function Markdown({ text }: { text: string }) {
  const content = useMemo(() => render(text), [text])
  return <div className="markdown">{content}</div>
}
