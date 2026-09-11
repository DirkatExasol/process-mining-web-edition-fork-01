/** Sankey flow view for the A-Chart / B-Chart.
 *
 *  A left-to-right flow diagram of the process: band width is proportional to how many
 *  journeys take each transition. Loops are removed by collapsing each looping cluster of
 *  steps into one node (see graph/sankey.ts), so the picture reads as a clean flow instead
 *  of a tangle of back-edges. Hover a band or a node for exact counts; the rest dims.
 *
 *  Self-contained SVG (no ReactFlow) so it scales to the container and themes with the app
 *  tokens. Node vertical order is refined with a couple of barycentre sweeps to cut crossings.
 */

import { useMemo, useState } from 'react'
import { ACCENT, groupColor, namedColor } from '../graph/colors'
import { formatCount, formatDuration, formatPercent } from '../graph/format'
import { buildSankey, type SankeyLink, type SankeyModel, type SankeyNode } from '../graph/sankey'
import type { ProcessGraph, TransitionMetric } from '../types'

// Virtual coordinate system; the SVG viewBox scales it to the pane. Exported so the
// server-report SVG generator (sankeySvg.ts) reuses the exact same geometry.
export const H = 780
const TOP = 30
const BOTTOM = 40
export const NODE_W = 15
const NODE_PAD = 16 // vertical gap between stacked nodes in a column
const MARGIN_L = 96
const MARGIN_R = 70
const COL_STRIDE = 205

export interface Placed extends SankeyNode {
  x: number
  y: number
  h: number
  color: string
}
export interface Ribbon {
  key: string
  d: string
  color: string
  source: string
  target: string
  /** Occurrences (journeys) on this flow — always available for context. */
  occ: number
  /** The value in the *selected metric* — what the band width and label encode. */
  label: string
  /** occ as a share of the source node's total outflow, for the tooltip. */
  occShare: number
}

/** The value the *selected metric* assigns to a link — this is what drives band width.
 *  Count → occurrences; the two percentages → shares; time metrics → seconds. */
function metricValueOf(
  l: SankeyLink,
  metric: TransitionMetric,
  srcOutOcc: number,
  journeyTotal: number,
): number {
  switch (metric) {
    case 'Percentage':
      return srcOutOcc > 0 ? (l.value / srcOutOcc) * 100 : 0
    case 'Journey %':
      return journeyTotal > 0 ? (l.value / journeyTotal) * 100 : 0
    case 'Avg Time':
      return l.avgSecs ?? 0
    case 'Min Time':
      return l.minSecs ?? 0
    case 'Max Time':
      return l.maxSecs ?? 0
    case 'Std Dev':
      return l.stdDevSecs ?? 0
    default:
      return l.value // Count
  }
}

/** Human label for a link under the selected metric. */
function metricLabelOf(l: SankeyLink, metric: TransitionMetric, value: number): string {
  if (metric === 'Count') return formatCount(l.value)
  if (metric === 'Percentage' || metric === 'Journey %') return formatPercent(value)
  const raw =
    metric === 'Avg Time'
      ? l.avgSecs
      : metric === 'Min Time'
        ? l.minSecs
        : metric === 'Max Time'
          ? l.maxSecs
          : l.stdDevSecs
  return raw == null ? '—' : formatDuration(value)
}

type Hover =
  | { kind: 'node'; node: Placed }
  | { kind: 'link'; ribbon: Ribbon }
  | null

function colorFor(node: SankeyNode, graph: ProcessGraph): string {
  const first = graph.steps[node.members[0]]
  // A grouped node takes its step group's colour; a plain node its own fill. A concrete
  // hex fallback (not a CSS var) so the same colour survives into the standalone report SVG.
  if (first?.belongsTo) return groupColor(first.belongsTo)
  if (first?.bgColor) return namedColor(first.bgColor)
  return ACCENT
}

/** Position nodes into columns and turn links into ribbon paths, sized by the metric.
 *  Pure — shared by the React view and the server-report SVG generator. */
export function layoutSankey(
  model: SankeyModel,
  graph: ProcessGraph,
  metric: TransitionMetric,
  journeyTotal: number,
): { nodes: Placed[]; ribbons: Ribbon[]; width: number } {
  const { nodes, links, columns } = model
  if (nodes.length === 0) return { nodes: [], ribbons: [], width: 800 }

  const width = MARGIN_L + Math.max(0, columns - 1) * COL_STRIDE + MARGIN_R
  const colX = (c: number) => MARGIN_L + c * COL_STRIDE

  // Per-link value in the selected metric (this is what band widths encode). If the metric
  // yields nothing anywhere (e.g. a time metric with no timing data), fall back to counts
  // so the diagram still renders.
  const srcOutOcc = new Map<string, number>()
  for (const l of links) srcOutOcc.set(l.source, (srcOutOcc.get(l.source) ?? 0) + l.value)
  let mv = new Map<string, number>(
    links.map((l) => [`${l.source}->${l.target}`, metricValueOf(l, metric, srcOutOcc.get(l.source) ?? 0, journeyTotal)]),
  )
  if ([...mv.values()].every((v) => v <= 0)) {
    mv = new Map(links.map((l) => [`${l.source}->${l.target}`, l.value]))
  }
  const linkVal = (l: SankeyLink) => mv.get(`${l.source}->${l.target}`) ?? 0

  // Node "size" (bar height) = the heavier of its metric inflow / outflow, so ribbons stack
  // into it. (The printed number stays the occurrence throughput, node.volume.)
  const inV = new Map<string, number>()
  const outV = new Map<string, number>()
  for (const l of links) {
    outV.set(l.source, (outV.get(l.source) ?? 0) + linkVal(l))
    inV.set(l.target, (inV.get(l.target) ?? 0) + linkVal(l))
  }
  const sizeOf = (id: string) => Math.max(inV.get(id) ?? 0, outV.get(id) ?? 0) || 0.0001

  const byCol: SankeyNode[][] = Array.from({ length: columns }, () => [])
  for (const n of nodes) byCol[n.column].push(n)

  // One shared px-per-unit scale so widths are comparable across columns, chosen so the
  // tallest column still fits the height.
  let scale = Infinity
  for (const col of byCol) {
    if (col.length === 0) continue
    const flow = col.reduce((a, n) => a + sizeOf(n.id), 0)
    const avail = H - TOP - BOTTOM - (col.length - 1) * NODE_PAD
    if (flow > 0) scale = Math.min(scale, avail / flow)
  }
  if (!Number.isFinite(scale)) scale = 1

  const order = new Map<string, number>()
  // Seed order by descending size within each column.
  for (const col of byCol) {
    col.sort((a, b) => sizeOf(b.id) - sizeOf(a.id))
    col.forEach((n, i) => order.set(n.id, i))
  }

  const yById = new Map<string, { y: number; h: number }>()
  const placeColumn = (col: SankeyNode[]) => {
    const stackH = col.reduce((a, n) => a + Math.max(sizeOf(n.id) * scale, 2), 0) + (col.length - 1) * NODE_PAD
    let y = TOP + Math.max(0, (H - TOP - BOTTOM - stackH) / 2)
    for (const n of col) {
      const h = Math.max(sizeOf(n.id) * scale, 2)
      yById.set(n.id, { y, h })
      y += h + NODE_PAD
    }
  }
  byCol.forEach(placeColumn)

  // Barycentre sweeps: reorder each column by the mean centre-y of its neighbours, cutting
  // crossings. Forward (by predecessors) then backward (by successors), twice.
  const inNb = new Map<string, Array<{ id: string; w: number }>>()
  const outNb = new Map<string, Array<{ id: string; w: number }>>()
  for (const l of links) {
    ;(inNb.get(l.target) ?? inNb.set(l.target, []).get(l.target)!).push({ id: l.source, w: l.value })
    ;(outNb.get(l.source) ?? outNb.set(l.source, []).get(l.source)!).push({ id: l.target, w: l.value })
  }
  const centre = (id: string) => {
    const p = yById.get(id)!
    return p.y + p.h / 2
  }
  const bary = (id: string, nb: Map<string, Array<{ id: string; w: number }>>) => {
    const list = nb.get(id)
    if (!list || list.length === 0) return centre(id)
    let sw = 0
    let acc = 0
    for (const { id: nid, w } of list) {
      acc += centre(nid) * w
      sw += w
    }
    return sw > 0 ? acc / sw : centre(id)
  }
  for (let sweep = 0; sweep < 2; sweep++) {
    for (let c = 1; c < columns; c++) {
      byCol[c].sort((a, b) => bary(a.id, inNb) - bary(b.id, inNb))
      placeColumn(byCol[c])
    }
    for (let c = columns - 2; c >= 0; c--) {
      byCol[c].sort((a, b) => bary(a.id, outNb) - bary(b.id, outNb))
      placeColumn(byCol[c])
    }
  }
  byCol.forEach((col) => col.forEach((n, i) => order.set(n.id, i)))

  const placed: Placed[] = nodes.map((n) => {
    const p = yById.get(n.id)!
    return { ...n, x: colX(n.column), y: p.y, h: p.h, color: colorFor(n, graph) }
  })
  const placedById = new Map(placed.map((p) => [p.id, p]))
  const centreY = (id: string) => {
    const p = placedById.get(id)!
    return p.y + p.h / 2
  }

  // Stack ribbon endpoints along each node edge, sorted by the opposite endpoint's centre.
  const outAcc = new Map<string, number>()
  const inAcc = new Map<string, number>()
  for (const p of placed) {
    outAcc.set(p.id, p.y)
    inAcc.set(p.id, p.y)
  }
  const ribbons: Ribbon[] = links
    .slice()
    .sort((a, b) => {
      // Group by source, then by target y — deterministic stacking.
      if (a.source !== b.source) return centreY(a.source) - centreY(b.source)
      return centreY(a.target) - centreY(b.target)
    })
    .map((l) => {
      const s = placedById.get(l.source)!
      const w = Math.max(linkVal(l) * scale, 1)
      const sy = outAcc.get(l.source)!
      outAcc.set(l.source, sy + w)
      return { l, s, w, sy }
    })
    // Assign target-side offsets in target-then-source order for a tidy right edge.
    .sort((a, b) => {
      if (a.l.target !== b.l.target) return centreY(a.l.target) - centreY(b.l.target)
      return centreY(a.l.source) - centreY(b.l.source)
    })
    .map(({ l, s, w, sy }) => {
      const t = placedById.get(l.target)!
      const ty = inAcc.get(l.target)!
      inAcc.set(l.target, ty + w)
      const sx = s.x + NODE_W
      const tx = t.x
      const mx = (sx + tx) / 2
      const s0 = sy
      const s1 = sy + w
      const t0 = ty
      const t1 = ty + w
      const d = `M${sx},${s0} C${mx},${s0} ${mx},${t0} ${tx},${t0} L${tx},${t1} C${mx},${t1} ${mx},${s1} ${sx},${s1} Z`
      const src = srcOutOcc.get(l.source) ?? l.value
      return {
        key: `${l.source}->${l.target}`,
        d,
        color: s.color,
        source: l.source,
        target: l.target,
        occ: l.value,
        label: metricLabelOf(l, metric, linkVal(l)),
        occShare: src > 0 ? (l.value / src) * 100 : 0,
      }
    })

  return { nodes: placed, ribbons, width }
}

export function SankeyChart({
  graph,
  metric = 'Count',
  journeyTotal = 0,
}: {
  graph: ProcessGraph
  metric?: TransitionMetric
  journeyTotal?: number
}) {
  const model = useMemo(() => buildSankey(graph), [graph])
  const { nodes, ribbons, width } = useMemo(
    () => layoutSankey(model, graph, metric, journeyTotal),
    [model, graph, metric, journeyTotal],
  )
  const [hover, setHover] = useState<Hover>(null)
  const [tip, setTip] = useState<{ x: number; y: number; html: React.ReactNode } | null>(null)

  const total = useMemo(() => nodes.reduce((m, n) => Math.max(m, n.volume), 0) || 1, [nodes])

  const dimLink = (r: Ribbon): boolean => {
    if (!hover) return false
    if (hover.kind === 'link') return hover.ribbon.key !== r.key
    return hover.node.id !== r.source && hover.node.id !== r.target
  }
  const dimNode = (n: Placed): boolean => {
    if (!hover) return false
    if (hover.kind === 'node') return hover.node.id !== n.id
    return hover.ribbon.source !== n.id && hover.ribbon.target !== n.id
  }

  const move = (e: React.MouseEvent, html: React.ReactNode) =>
    setTip({ x: Math.min(e.clientX + 14, window.innerWidth - 300), y: e.clientY + 16, html })

  if (nodes.length === 0) {
    return (
      <div className="sankey-wrap">
        <div className="center-fill">
          <span className="fg-secondary">Nothing to flow — no transitions.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="sankey-wrap">
      <div className="sankey-scroll">
        <svg
          className="sankey-svg"
          viewBox={`0 0 ${width} ${H}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="Sankey flow of the process transitions"
        >
          {ribbons.map((r) => (
            <path
              key={r.key}
              d={r.d}
              className={`sankey-link${dimLink(r) ? ' dim' : ''}`}
              fill={r.color}
              onMouseEnter={() => setHover({ kind: 'link', ribbon: r })}
              onMouseLeave={() => {
                setHover(null)
                setTip(null)
              }}
              onMouseMove={(e) =>
                move(
                  e,
                  <>
                    <span className="sankey-tip-big">{r.label}</span>
                    <b>{labelOf(r.source, nodes)}</b> → <b>{labelOf(r.target, nodes)}</b>
                    <br />
                    <span className="sankey-tip-mut">
                      {pct(r.occShare, 100)}% of {labelOf(r.source, nodes)} outflow ·{' '}
                      {formatCount(r.occ)} journeys
                    </span>
                  </>,
                )
              }
            />
          ))}

          {nodes.map((n) => {
            const lastCol = Math.max(...nodes.map((m) => m.column))
            const right = n.column < lastCol
            const tx = right ? n.x + NODE_W + 7 : n.x - 7
            const cy = n.y + Math.max(n.h, 14) / 2
            const isFocus = hover?.kind === 'node' && hover.node.id === n.id
            return (
              <g
                key={n.id}
                className={`sankey-node${dimNode(n) ? ' dim' : ''}${isFocus ? ' focus' : ''}${
                  n.isCluster ? ' cluster' : ''
                }`}
                onMouseEnter={() => setHover({ kind: 'node', node: n })}
                onMouseLeave={() => {
                  setHover(null)
                  setTip(null)
                }}
                onMouseMove={(e) =>
                  move(
                    e,
                    <>
                      <span className="sankey-tip-big">
                        {n.isCluster ? `↺ ${n.label}` : n.label}
                      </span>
                      <b>{formatCount(n.volume)}</b> journeys · <span className="sankey-tip-mut">{pct(n.volume, total)}% of peak</span>
                      {n.isCluster && (
                        <div className="sankey-tip-members">
                          <div className="sankey-tip-mut">
                            Grouped steps that loop together ({n.members.length}):
                          </div>
                          <ul>
                            {n.members.map((m) => (
                              <li key={m}>{m}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {n.internalHops > 0 && (
                        <div className="sankey-tip-mut" style={{ marginTop: 2 }}>
                          ↺ {formatCount(n.internalHops)} internal loops between them
                        </div>
                      )}
                    </>,
                  )
                }
              >
                <rect x={n.x} y={n.y} width={NODE_W} height={Math.max(n.h, 2)} rx={2.5} fill={n.color} />
                <text
                  className="sankey-nlabel"
                  x={tx}
                  y={cy - 2}
                  textAnchor={right ? 'start' : 'end'}
                >
                  {n.isCluster ? `↺ ${n.label}` : n.label}
                </text>
                <text
                  className="sankey-ncount"
                  x={tx}
                  y={cy + 11}
                  textAnchor={right ? 'start' : 'end'}
                >
                  {formatCount(n.volume)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="sankey-foot">
        Band width shows <b>{metric}</b>.
        {model.clustered > 0 && (
          <>
            {' '}
            {model.clustered} looping cluster{model.clustered === 1 ? '' : 's'} collapsed for
            readability — marked ↺; hover to see the members and internal-loop counts.
          </>
        )}
      </div>

      {tip && (
        <div className="sankey-tip" style={{ left: tip.x, top: tip.y }}>
          {tip.html}
        </div>
      )}
    </div>
  )
}

function labelOf(id: string, nodes: Placed[]): string {
  return nodes.find((n) => n.id === id)?.label ?? id
}
function pct(v: number, of: number): string {
  if (of <= 0) return '0'
  const p = (v / of) * 100
  return p >= 10 ? String(Math.round(p)) : p.toFixed(1)
}
