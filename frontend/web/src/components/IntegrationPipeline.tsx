/** The import pipeline as ONE live flowchart. Nodes are **reused** across runs: every
 *  distinct source type, source and destination connection is a single node, and the
 *  Abstraction layer is the one hub in the middle. As imports happen over time the same
 *  graph accumulates — edges connect whatever combinations have run, the Source and
 *  Destination nodes carry the **total imported rows**, and the currently-running path
 *  lights up. Driven by the run history (which folds in the live status), so it reflects
 *  any import — manual, watchdog or API-push — and keeps the behaviour over time in view.
 *
 *      [Source type] ──▶ [Source] ──▶ [Abstraction layer] ──▶ [Connection]
 *      (one node per distinct name; many sources/types/destinations fan in and out)
 */

import {
  Background,
  BackgroundVariant,
  BaseEdge,
  getBezierPath,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useMemo } from 'react'
import { useStore } from '../store'
import { flowKeyframes } from '../flow/MetricEdge'
import type { IntegrationStatus } from '../types'
import type { PipelineRun } from '../integration/runHistory'

/** The subset of the layer status the pipeline needs from the live run (progress). */
export interface PipelineView {
  state: 'idle' | 'running' | 'completed' | 'failed'
  sourceName: string | null
  sourceTypeName: string | null
  extractorName?: string | null
  connectionName: string | null
  connectionId?: string | null
  schema: string | null
  recordsPushed: number
  recordsDone: number
  recordsTotal: number
  lastError: string | null
  activeConnectionId?: string | null
  activeSchema?: string | null
  connected?: boolean
}

type Phase = 'idle' | 'active' | 'done' | 'error'

interface PipeData {
  icon: string
  kicker: string
  title: string
  subtitle?: string
  accent: string
  phase: Phase
  ports: Array<'l' | 'r'>
  rows?: number | null // imported row total shown on Source / Destination nodes
  // Abstraction-layer hub only:
  stateLabel?: string
  progress?: { done: number; total: number } | null
  [key: string]: unknown
}

const STATE_LABEL: Record<string, string> = {
  idle: 'Idle', running: 'Running', completed: 'Completed', failed: 'Failed',
}

const phaseOf = (state: string): Phase =>
  state === 'running' ? 'active' : state === 'failed' ? 'error' : state === 'idle' ? 'idle' : 'done'

const accentFor = (p: Phase): string =>
  p === 'active' ? 'var(--accent)' : p === 'error' ? 'var(--red)' : p === 'done' ? 'var(--green)' : 'var(--secondary)'

function PipeNode({ data }: NodeProps) {
  const d = data as PipeData
  return (
    <div className={`ipipe-node ${d.phase}`} style={{ opacity: d.phase === 'idle' ? 0.72 : 1 }}>
      {d.ports.includes('l') && <Handle type="target" position={Position.Left} id="l" className="ipipe-handle" />}
      <div className="ipipe-row">
        <span className="ipipe-icon" style={{ background: `color-mix(in srgb, transparent, ${d.accent} 20%)`, color: d.accent }}>
          {d.icon}
        </span>
        <div className="ipipe-text">
          <span className="ipipe-kicker">{d.kicker}</span>
          <span className="ipipe-title" title={d.title}>{d.title}</span>
          {d.subtitle && <span className="ipipe-sub" title={d.subtitle}>{d.subtitle}</span>}
        </div>
      </div>

      {d.rows != null && (
        <div className="ipipe-rows">▦ {d.rows.toLocaleString()} rows imported</div>
      )}

      {d.stateLabel !== undefined && (
        <div className="ipipe-layer">
          <div className="iprogress-track" style={{ marginTop: 2 }}>
            <div
              className={`iprogress-fill${
                d.phase === 'active' && !(d.progress && d.progress.total > 0) ? ' indeterminate' : ''
              }`}
              style={
                d.progress && d.progress.total > 0
                  ? { width: `${Math.min(100, (d.progress.done / d.progress.total) * 100)}%` }
                  : d.phase === 'active'
                    ? undefined
                    : { width: d.phase === 'done' ? '100%' : '0%' }
              }
            />
          </div>
          <span className="ipipe-sub">{d.stateLabel}</span>
        </div>
      )}

      {d.ports.includes('r') && <Handle type="source" position={Position.Right} id="r" className="ipipe-handle" />}
    </div>
  )
}

const nodeTypes = { pipe: PipeNode }

const FLOW_SECS_PER_EDGE = 0.9 // dot travel time per edge; the run's path loops over N×this

interface PipeEdgeData {
  active?: boolean
  flowIndex?: number
  flowTotal?: number
  stroke?: string
  width?: number
  [key: string]: unknown
}

/** Edge that always draws its connection line and, while the run is active, sends a
 *  single dot travelling the run's path node-to-node in order — the pipeline's take on
 *  the main app's Individual Journey playback (shared `flowKeyframes`). */
function PipeEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const d = (data ?? {}) as PipeEdgeData
  const [path] = getBezierPath({
    sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
  })
  return (
    <>
      <BaseEdge id={id} path={path} style={{ stroke: d.stroke ?? 'var(--border)', strokeWidth: d.width ?? 1.5 }} />
      {d.active && d.flowTotal
        ? (() => {
            const total = d.flowTotal * FLOW_SECS_PER_EDGE
            const kf = flowKeyframes(d.flowIndex ?? 0, d.flowTotal)
            return (
              <circle r={5} fill="var(--accent)" stroke="#fff" strokeWidth={1.5} opacity={0}>
                <animateMotion
                  dur={`${total}s`}
                  repeatCount="indefinite"
                  calcMode="linear"
                  keyPoints={kf.keyPoints}
                  keyTimes={kf.keyTimes}
                  path={path}
                />
                <animate
                  attributeName="opacity"
                  dur={`${total}s`}
                  repeatCount="indefinite"
                  calcMode="discrete"
                  keyTimes={kf.opacityTimes}
                  values={kf.opacityValues}
                />
              </circle>
            )
          })()
        : null}
    </>
  )
}

const edgeTypes = { pipe: PipeEdge }

const GAP = 118
const COL_X = { type: 0, src: 235, layer: 470, conn: 705 }
const NODE_W = 210
const NODE_H = 112
// Declared size on every node so ReactFlow keeps each node's handle bounds when the
// pipeline is rebuilt on each status poll (new object refs). Without it the nodes flip
// to visibility:hidden mid-measure and their edges drop out — see FlowChart's note.
const NODE_DIMS = {
  measured: { width: NODE_W, height: NODE_H },
  initialWidth: NODE_W,
  initialHeight: NODE_H,
}

export function IntegrationPipeline({
  runs,
  live,
}: {
  runs: PipelineRun[]
  live: IntegrationStatus | null
}) {
  const connections = useStore((s) => s.connections)

  const { nodes, edges, canvasH } = useMemo(() => {
    // ── Aggregate the whole history into ONE graph (reuse nodes by name) ──────
    const typeOrder: string[] = []
    const srcOrder: string[] = []
    const connOrder: string[] = []
    const push = (arr: string[], v: string) => { if (!arr.includes(v)) arr.push(v) }

    const srcRows = new Map<string, number>()
    const connRows = new Map<string, number>()
    const connSchema = new Map<string, string | null>()
    const nodePhase = new Map<string, Phase>() // node id → latest phase
    const edgePhase = new Map<string, Phase>() // edge key → latest phase (colours the edge)
    const edgeSet = new Set<string>() // "from||to"
    let running: PipelineRun | null = null
    let totalRows = 0

    const typeId = (n: string) => `type:${n}`
    const srcId = (n: string) => `src:${n}`
    const connId = (n: string) => `conn:${n}`

    // Oldest → newest so the latest run's state/schema wins the maps.
    for (const r of [...runs].reverse()) {
      const tName = r.sourceTypeName || '(no source type)'
      const sName = r.sourceName || '(source)'
      const cName = r.connectionName || r.schema || '(destination)'
      push(typeOrder, tName)
      push(srcOrder, sName)
      push(connOrder, cName)

      const rows = r.recordsPushed || 0
      totalRows += rows
      srcRows.set(sName, (srcRows.get(sName) ?? 0) + rows)
      connRows.set(cName, (connRows.get(cName) ?? 0) + rows)
      connSchema.set(cName, r.schema)

      const ph = phaseOf(r.state)
      nodePhase.set(typeId(tName), ph)
      nodePhase.set(srcId(sName), ph)
      nodePhase.set(connId(cName), ph)

      const e1 = `${typeId(tName)}||${srcId(sName)}`
      const e2 = `${srcId(sName)}||layer`
      const e3 = `layer||${connId(cName)}`
      edgeSet.add(e1); edgeSet.add(e2); edgeSet.add(e3)
      // Newest run touching an edge wins its colour (running→green, failed→red, else blue).
      edgePhase.set(e1, ph); edgePhase.set(e2, ph); edgePhase.set(e3, ph)
      if (r.state === 'running') running = r
    }

    // Empty history → a dim skeleton so the pipeline's shape is always visible, with
    // the active connection (if any) as the destination.
    const empty = runs.length === 0
    if (empty) {
      typeOrder.push('Source type')
      srcOrder.push('Source')
      const connName = live?.activeConnectionId
        ? connections.find((c) => c.id === live.activeConnectionId)?.name ?? live.activeSchema ?? '(no connection)'
        : live?.activeSchema ?? '(no connection)'
      connOrder.push(connName)
      connSchema.set(connName, live?.activeSchema ?? null)
      for (const id of [typeId('Source type'), srcId('Source'), 'layer', connId(connName)]) {
        nodePhase.set(id, 'idle')
      }
      for (const e of [
        `${typeId('Source type')}||${srcId('Source')}`,
        `${srcId('Source')}||layer`,
        `layer||${connId(connName)}`,
      ]) {
        edgeSet.add(e)
        edgePhase.set(e, 'idle')
      }
    }

    const maxCount = Math.max(typeOrder.length, srcOrder.length, connOrder.length, 1)
    const centerY = ((maxCount - 1) * GAP) / 2
    const colY = (count: number, i: number) => centerY - ((count - 1) * GAP) / 2 + i * GAP

    // The hub reflects the newest run's outcome (or the running one).
    const layerPhase: Phase = running
      ? 'active'
      : empty
        ? 'idle'
        : runs[0]
          ? phaseOf(runs[0].state)
          : 'done'

    const nodes: Node[] = []

    typeOrder.forEach((name, i) => {
      const ph = nodePhase.get(typeId(name)) ?? 'done'
      nodes.push({
        id: typeId(name), type: 'pipe', draggable: false, ...NODE_DIMS,
        position: { x: COL_X.type, y: colY(typeOrder.length, i) },
        data: {
          icon: '🧩', kicker: 'Source type', title: name,
          subtitle: 'extraction spec', accent: 'var(--purple, #9b59d0)', phase: ph, ports: ['r'],
        } satisfies PipeData,
      })
    })

    srcOrder.forEach((name, i) => {
      const ph = nodePhase.get(srcId(name)) ?? 'done'
      nodes.push({
        id: srcId(name), type: 'pipe', draggable: false, ...NODE_DIMS,
        position: { x: COL_X.src, y: colY(srcOrder.length, i) },
        data: {
          icon: '🗂️', kicker: 'Source', title: name,
          subtitle: 'imported & extracted', accent: 'var(--accent)', phase: ph, ports: ['l', 'r'],
          rows: empty ? null : srcRows.get(name) ?? 0,
        } satisfies PipeData,
      })
    })

    nodes.push({
      id: 'layer', type: 'pipe', draggable: false, ...NODE_DIMS,
      position: { x: COL_X.layer, y: centerY },
      data: {
        icon: '⚙️', kicker: 'Abstraction layer', title: 'Ingest & normalise',
        accent: accentFor(layerPhase), phase: layerPhase, ports: ['l', 'r'],
        stateLabel: running
          ? STATE_LABEL.running
          : empty
            ? 'Idle'
            : `${totalRows.toLocaleString()} rows over ${runs.length} run${runs.length === 1 ? '' : 's'}`,
        progress: running ? { done: running.recordsDone ?? 0, total: running.recordsTotal ?? 0 } : null,
      } satisfies PipeData,
    })

    connOrder.forEach((name, i) => {
      const ph = nodePhase.get(connId(name)) ?? 'done'
      const schema = connSchema.get(name)
      nodes.push({
        id: connId(name), type: 'pipe', draggable: false, ...NODE_DIMS,
        position: { x: COL_X.conn, y: colY(connOrder.length, i) },
        data: {
          icon: '🛢️', kicker: 'Connection', title: name,
          subtitle: schema ? `schema ${schema}` : 'destination database',
          accent: 'var(--teal, #1a9e8f)', phase: ph, ports: ['l'],
          rows: empty ? null : connRows.get(name) ?? 0,
        } satisfies PipeData,
      })
    })

    const edges: Edge[] = [...edgeSet].map((key) => {
      const [source, target] = key.split('||')
      const ph = edgePhase.get(key) ?? 'done'
      const active = ph === 'active'
      // Colour by the edge's latest run: running → green, failed → red, else blue.
      const stroke =
        ph === 'active' ? 'var(--green)' : ph === 'error' ? 'var(--red)' : 'var(--blue, #3b82f6)'
      // Position in the run's path so a single dot hops type→source→layer→conn in order.
      const flowIndex = source.startsWith('type:') ? 0 : source.startsWith('src:') ? 1 : 2
      return {
        id: key, source, target, sourceHandle: 'r', targetHandle: 'l',
        type: 'pipe',
        data: {
          active,
          flowIndex,
          flowTotal: 3,
          stroke,
          width: active ? 2.6 : 2,
        } satisfies PipeEdgeData,
      }
    })

    const canvasH = Math.max(300, maxCount * GAP + 70)
    return { nodes, edges, canvasH }
  }, [runs, live, connections])

  return (
    <div className="ipipe-canvas" style={{ height: canvasH }}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.16 }}
          nodesConnectable={false}
          nodesDraggable={false}
          elementsSelectable={false}
          panOnDrag
          zoomOnScroll={false}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={1.5}
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  )
}
