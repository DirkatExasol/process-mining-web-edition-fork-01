/** Swimlane view for a single Individual Journey.
 *
 *  Where the flowchart aggregates a case into a directed-follows graph (with loops), the
 *  swimlane lays the journey out **strictly sequentially**: one column per event in time
 *  order, so a revisited step simply appears again — loops are unrolled by construction.
 *  Each **lane is a node group** (a step's `belongsTo`), tinted with the group's colour;
 *  a step sits in its group's lane. A header row above the top lane carries each event's
 *  **date/time**, and each edge carries the **time from one node to the next**.
 *
 *  This is only meaningful for a single journey — it is never used for aggregated views.
 */

import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type Viewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCallback, useMemo, useState } from 'react'

import { groupColor } from '../graph/colors'
import { formatDateShort, formatDuration, formatTimeOnly } from '../graph/format'
import type { JourneyEvent, ProcessGraph } from '../types'

const COL_W = 210 // horizontal spacing between consecutive events
const NODE_W = 150
const NODE_H = 46
const LANE_H = 96
const HEADER_H = 40 // the date/time row above the top lane
const PAD_X = 150 // left gutter that carries the lane labels
const UNGROUPED = '(ungrouped)'
const CHART_H = 210 // the cumulative-value line chart below the lanes
const CHART_GAP = 18 // gap between the last lane and the value chart
const CHART_LABEL_FS = 16 // axis + value numbers (50% larger than the old 11px)

// ── node payloads ─────────────────────────────────────────────────────────────

interface LaneData extends Record<string, unknown> {
  label: string
  color: string
  width: number
  header?: boolean
}
interface StepData extends Record<string, unknown> {
  label: string
  bg: string
  fg: string
  border: string
}
interface TimeData extends Record<string, unknown> {
  time: string
  date: string
}
interface GridData extends Record<string, unknown> {
  height: number
}
export interface ValuePoint {
  cx: number // absolute x (aligned to the step column centre)
  value: number // this step's own score (the +/- contribution)
  cumulative: number // running sum from the process start
}
interface ChartData extends Record<string, unknown> {
  width: number
  height: number
  points: ValuePoint[]
  min: number
  max: number
}

function LaneNode({ data }: { data: LaneData }) {
  // Solid, theme-aware bands: each lane is its group colour mixed into the surface (not
  // over transparency), so neighbouring lanes read as clearly distinct rows in both
  // themes. A strong separator line divides them, and a coloured spine marks the left.
  return (
    <div
      className={`swim-lane${data.header ? ' header' : ''}`}
      style={{
        width: data.width,
        height: data.header ? HEADER_H : LANE_H,
        background: data.header
          ? 'var(--bg-tertiary-grouped)'
          : `color-mix(in srgb, ${data.color} 26%, var(--bg-secondary-grouped))`,
        borderLeft: data.header ? 'none' : `4px solid ${data.color}`,
      }}
    >
      <span
        className="swim-lane-label"
        style={{ color: data.header ? 'var(--secondary)' : 'var(--primary)' }}
      >
        {data.label}
      </span>
    </div>
  )
}

function StepNodeSwim({ data }: { data: StepData }) {
  return (
    <div
      className="swim-step"
      style={{
        width: NODE_W,
        height: NODE_H,
        background: data.bg,
        color: data.fg,
        border: `1.5px solid ${data.border}`,
      }}
      title={data.label}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <span className="swim-step-label">{data.label}</span>
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  )
}

function TimeNode({ data }: { data: TimeData }) {
  return (
    <div className="swim-time">
      <span className="swim-time-clock">{data.time}</span>
      <span className="swim-time-date">{data.date}</span>
    </div>
  )
}

function GridNode({ data }: { data: GridData }) {
  return <div className="swim-grid" style={{ height: data.height }} />
}

function fmtScore(n: number): string {
  const r = Math.round(n * 100) / 100
  return (r > 0 ? '+' : '') + (Number.isInteger(r) ? String(r) : r.toFixed(2))
}

// A cumulative-value line chart drawn below the lanes: for each event, the running sum of
// the step scores from the process start — so the journey's value can be read developing
// left→right. It is a ReactFlow node, so it pans/zooms with the lanes and each point stays
// aligned under its step column.
function ValueChartNode({ data }: { data: ChartData }) {
  const { width, height, points, min, max } = data
  const plotTop = 52
  const plotBot = height - 30
  const span = max - min || 1
  const yOf = (v: number) => plotBot - ((v - min) / span) * (plotBot - plotTop)
  const zeroY = min <= 0 && max >= 0 ? yOf(0) : null
  const linePath = points
    .map((p, i) => `${i ? 'L' : 'M'}${p.cx.toFixed(1)} ${yOf(p.cumulative).toFixed(1)}`)
    .join(' ')
  return (
    <div className="swim-valuechart" style={{ width, height }}>
      <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
        {/* Tinted panel that matches the swimlane's own bands (the header-band tone). */}
        <rect
          x={0}
          y={0}
          width={width}
          height={height}
          rx={10}
          fill="var(--bg-tertiary-grouped)"
          stroke="var(--separator-soft)"
        />
        <text x={14} y={24} fill="var(--primary)" fontSize={13} fontWeight={650}>
          Cumulative value — running sum of step scores from start to end
        </text>
        {/* y-axis extremes in the left gutter */}
        <text x={14} y={plotTop + 6} fill="var(--primary)" fontSize={CHART_LABEL_FS} fontWeight={600}>
          {fmtScore(max)}
        </text>
        <text x={14} y={plotBot + 4} fill="var(--primary)" fontSize={CHART_LABEL_FS} fontWeight={600}>
          {fmtScore(min)}
        </text>
        {/* per-column guide lines, aligned to the step centres */}
        {points.map((p) => (
          <line
            key={`g${p.cx}`}
            x1={p.cx}
            y1={plotTop}
            x2={p.cx}
            y2={plotBot}
            stroke="var(--separator-soft)"
            strokeWidth={1}
          />
        ))}
        {/* the zero baseline (only when the range crosses zero) */}
        {zeroY != null && (
          <line
            x1={PAD_X}
            y1={zeroY}
            x2={width - 8}
            y2={zeroY}
            stroke="var(--separator)"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        )}
        <path
          d={linePath}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {points.map((p) => {
          const y = yOf(p.cumulative)
          const dot =
            p.value > 0 ? 'var(--green)' : p.value < 0 ? 'var(--red)' : 'var(--secondary)'
          const above = y > plotTop + 20
          return (
            <g key={`m${p.cx}`}>
              <circle
                cx={p.cx}
                cy={y}
                r={4}
                fill={dot}
                stroke="var(--bg-elevated)"
                strokeWidth={1.5}
              />
              <text
                x={p.cx}
                y={above ? y - 11 : y + 20}
                textAnchor="middle"
                fill="var(--primary)"
                fontSize={CHART_LABEL_FS}
                fontWeight={600}
              >
                {fmtScore(p.cumulative)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

const nodeTypes = {
  swimLane: LaneNode,
  swimStep: StepNodeSwim,
  swimTime: TimeNode,
  swimGrid: GridNode,
  swimChart: ValueChartNode,
}

// ── layout ──────────────────────────────────────────────────────────────────

function secondsBetween(a: string, b: string): number | null {
  const ta = Date.parse(a)
  const tb = Date.parse(b)
  if (Number.isNaN(ta) || Number.isNaN(tb)) return null
  return Math.max(0, (tb - ta) / 1000)
}

// The running (YTD-style) sum of each step's score along the sequence, with the x of each
// point aligned to its step column's centre. `min`/`max` always include 0 so the baseline
// is on-chart. Exported for testing.
export function cumulativeSeries(
  sequence: JourneyEvent[],
  steps: ProcessGraph['steps'],
): { points: ValuePoint[]; min: number; max: number } {
  let running = 0
  const points: ValuePoint[] = sequence.map((ev, i) => {
    const value = steps[ev.step]?.score ?? 0
    running += value
    return { cx: PAD_X + i * COL_W + NODE_W / 2, value, cumulative: running }
  })
  const cums = points.map((p) => p.cumulative)
  return { points, min: Math.min(0, ...cums), max: Math.max(0, ...cums) }
}

export function buildSwimlane(
  sequence: JourneyEvent[],
  steps: ProcessGraph['steps'],
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []
  if (sequence.length === 0) return { nodes, edges }

  // Lanes = node groups, in first-appearance order.
  const laneOrder: string[] = []
  const groupOf = (step: string) => (steps[step]?.belongsTo || UNGROUPED)
  for (const ev of sequence) {
    const g = groupOf(ev.step)
    if (!laneOrder.includes(g)) laneOrder.push(g)
  }
  const totalWidth = PAD_X + sequence.length * COL_W

  // Every node declares its size (width/height + measured), like the flowchart's nodes:
  // ReactFlow renders a node visibility:hidden until it is measured, and its mocked
  // ResizeObserver never measures — see the reactflow-drag-hidden-nodes gotcha.
  const dims = (w: number, h: number) => ({ width: w, height: h, measured: { width: w, height: h } })

  // The date/time header band, then one coloured band per lane.
  nodes.push({
    id: 'lane:__header__',
    type: 'swimLane',
    position: { x: 0, y: 0 },
    data: { label: 'Date / time', color: 'var(--secondary)', width: totalWidth, header: true } as LaneData,
    draggable: false,
    selectable: false,
    zIndex: 0,
    ...dims(totalWidth, HEADER_H),
  })
  laneOrder.forEach((g, i) => {
    nodes.push({
      id: `lane:${g}`,
      type: 'swimLane',
      position: { x: 0, y: HEADER_H + i * LANE_H },
      data: { label: g, color: groupColor(g), width: totalWidth } as LaneData,
      draggable: false,
      selectable: false,
      zIndex: 0,
      ...dims(totalWidth, LANE_H),
    })
  })

  // Vertical gridlines between consecutive event columns, so the sequence is separated
  // horizontally as well as by lane. They span the header + lane stack, sit above the
  // opaque bands (z 1) and below the edges (z 2) and step nodes (z 3).
  const gridH = HEADER_H + laneOrder.length * LANE_H
  for (let i = 0; i < sequence.length - 1; i++) {
    const gx = PAD_X + i * COL_W + (NODE_W + COL_W) / 2
    nodes.push({
      id: `grid:${i}`,
      type: 'swimGrid',
      position: { x: gx, y: 0 },
      data: { height: gridH } as GridData,
      draggable: false,
      selectable: false,
      zIndex: 1,
      ...dims(1, gridH),
    })
  }

  // One step node + one time label per event, in order.
  sequence.forEach((ev, i) => {
    const x = PAD_X + i * COL_W
    const lane = laneOrder.indexOf(groupOf(ev.step))
    const info = steps[ev.step]
    const gc = groupColor(groupOf(ev.step))
    nodes.push({
      id: `t:${i}`,
      type: 'swimTime',
      position: { x: x + (NODE_W - 96) / 2, y: 6 },
      data: { time: formatTimeOnly(ev.eventTime), date: formatDateShort(ev.eventTime) } as TimeData,
      draggable: false,
      selectable: false,
      zIndex: 2,
      ...dims(96, HEADER_H - 8),
    })
    nodes.push({
      id: `n:${i}`,
      type: 'swimStep',
      position: { x, y: HEADER_H + lane * LANE_H + (LANE_H - NODE_H) / 2 },
      data: {
        label: ev.step,
        bg: info?.bgColor || gc,
        fg: info?.fgColor || '#ffffff',
        border: gc,
      } as StepData,
      draggable: false,
      selectable: false,
      zIndex: 3,
      ...dims(NODE_W, NODE_H),
    })
    if (i > 0) {
      const secs = secondsBetween(sequence[i - 1].eventTime, ev.eventTime)
      edges.push({
        id: `e:${i}`,
        source: `n:${i - 1}`,
        target: `n:${i}`,
        label: secs == null ? '' : formatDuration(secs),
        labelShowBg: true,
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 6,
        // A solid, theme-aware pill: an elevated surface with a hairline border, so the
        // duration reads clearly over the coloured lanes in both light and dark modes.
        labelBgStyle: {
          fill: 'var(--bg-elevated)',
          stroke: 'var(--separator)',
          strokeWidth: 1,
          fillOpacity: 1,
        },
        labelStyle: { fill: 'var(--primary)', fontSize: 11, fontWeight: 600 },
        style: { stroke: 'var(--primary)', strokeWidth: 1.5, opacity: 0.55 },
        // Above the opaque lane bands (z 0), below the step nodes (z 3), so the line and
        // its duration pill are never hidden behind a lane.
        zIndex: 2,
      })
    }
  })

  // The cumulative-value line chart, one full-width panel below the lane stack.
  const { points, min, max } = cumulativeSeries(sequence, steps)
  nodes.push({
    id: 'valuechart',
    type: 'swimChart',
    position: { x: 0, y: gridH + CHART_GAP },
    data: { width: totalWidth, height: CHART_H, points, min, max } as ChartData,
    draggable: false,
    selectable: false,
    zIndex: 2,
    ...dims(totalWidth, CHART_H),
  })

  return { nodes, edges }
}

// ── component ─────────────────────────────────────────────────────────────────

function SwimlaneInner({
  sequence,
  graph,
}: {
  sequence: JourneyEvent[]
  graph: ProcessGraph
}) {
  const { nodes, edges } = useMemo(
    () => buildSwimlane(sequence, graph.steps),
    [sequence, graph.steps],
  )

  // Zoom / fit / reset controls, mirroring the flowchart's (FlowChart.tsx). The swimlane
  // has no draggable node layout, so "reset" restores 100 % zoom rather than a saved layout.
  const flow = useReactFlow()
  const [zoom, setZoom] = useState(1)
  const onMove = useCallback((_: unknown, vp: Viewport) => setZoom(vp.zoom), [])
  const zoomBy = useCallback(
    (factor: number) => {
      const next = Math.max(0.1, Math.min(2, flow.getZoom() * factor))
      flow.zoomTo(next, { duration: 200 })
      setZoom(next)
    },
    [flow],
  )
  const fit = useCallback(() => flow.fitView({ padding: 0.15, duration: 300 }), [flow])
  const resetZoom = useCallback(() => {
    flow.zoomTo(1, { duration: 200 })
    setZoom(1)
  }, [flow])

  return (
    <div className="flow-wrap">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        onInit={(inst) => setZoom(inst.getZoom())}
        onMove={onMove}
        minZoom={0.1}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
      </ReactFlow>

      {/* Lower-right zoom cluster, matching the flowchart's controls. */}
      <div className="flow-overlay">
        <div className="zoom-controls">
          <button onClick={() => zoomBy(1 / 1.3)} title="Zoom out">−</button>
          <span className="zoom-value">{Math.round(zoom * 100)}%</span>
          <button onClick={() => zoomBy(1.3)} title="Zoom in">+</button>
          <button onClick={fit} title="Fit to view">⤢</button>
          <span className="sep" />
          <button onClick={resetZoom} title="Reset zoom (100%)">↺</button>
        </div>
      </div>
    </div>
  )
}

export function SwimlaneChart(props: { sequence: JourneyEvent[]; graph: ProcessGraph }) {
  return (
    <ReactFlowProvider>
      <SwimlaneInner {...props} />
    </ReactFlowProvider>
  )
}
