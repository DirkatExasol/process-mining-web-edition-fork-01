/** Render the process Sankey as a **self-contained** SVG string for the AI report.
 *
 *  The on-screen SankeyChart relies on the app's CSS tokens and classes (theme-aware). A
 *  report is a standalone HTML document that Python assembles and the browser prints, so it
 *  can't see those tokens — every colour and text style here is therefore inlined as a
 *  concrete value. Geometry is the exact same layout the on-screen chart uses (imported),
 *  so the printed diagram matches what the user saw.
 */

import { buildSankey } from '../graph/sankey'
import { H, NODE_W, layoutSankey } from './SankeyChart'
import type { ProcessGraph, TransitionMetric } from '../types'

const esc = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string)

/** A standalone `<svg>…</svg>` string of the Sankey, or '' when there's nothing to draw. */
export function sankeySvg(
  graph: ProcessGraph,
  metric: TransitionMetric,
  journeyTotal: number,
): string {
  const model = buildSankey(graph)
  const { nodes, ribbons, width } = layoutSankey(model, graph, metric, journeyTotal)
  if (nodes.length === 0) return ''

  const lastCol = Math.max(...nodes.map((n) => n.column))

  const bands = ribbons
    .map(
      (r) =>
        `<path d="${r.d}" fill="${esc(r.color)}" fill-opacity="0.42"/>`,
    )
    .join('')

  const HALO = '#ffffff'
  const INK = '#1a1a1a'
  const MUTED = '#6b6b72'
  const marks = nodes
    .map((n) => {
      const right = n.column < lastCol
      const tx = right ? n.x + NODE_W + 7 : n.x - 7
      const anchor = right ? 'start' : 'end'
      const cy = n.y + Math.max(n.h, 14) / 2
      const label = esc(n.isCluster ? `↺ ${n.label}` : n.label)
      const count = esc(formatCountLocal(n.volume))
      return (
        `<rect x="${n.x}" y="${n.y}" width="${NODE_W}" height="${Math.max(n.h, 2)}" rx="2.5" ` +
        `fill="${esc(n.color)}" stroke="#fcfcfb" stroke-width="1"/>` +
        `<text x="${tx}" y="${cy - 2}" text-anchor="${anchor}" font-size="12" font-weight="600" ` +
        `fill="${INK}" stroke="${HALO}" stroke-width="3" paint-order="stroke" stroke-linejoin="round">${label}</text>` +
        `<text x="${tx}" y="${cy + 11}" text-anchor="${anchor}" font-size="11" ` +
        `fill="${MUTED}" stroke="${HALO}" stroke-width="3" paint-order="stroke" stroke-linejoin="round">${count}</text>`
      )
    })
    .join('')

  return (
    `<svg viewBox="0 0 ${width} ${H}" xmlns="http://www.w3.org/2000/svg" ` +
    `font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif" ` +
    `role="img" aria-label="Process flow (Sankey)">${bands}${marks}</svg>`
  )
}

/** Local copy of the compact count format (avoids importing the whole format module chain
 *  for a one-liner, and keeps the report SVG self-contained). */
function formatCountLocal(n: number): string {
  if (n < 1_000) return `${n}`
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(1)}M`
}
