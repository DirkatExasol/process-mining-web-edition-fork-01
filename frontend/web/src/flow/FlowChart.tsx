import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type Viewport,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'

import {
  EDGE_SCHEMA_GRADIENTS,
  groupColor as groupColorFor,
  interpolate,
  type EdgeColorSchema,
} from '../graph/colors'
import { EdgeColorWizard } from './EdgeColorWizard'
import {
  GRID_SIZE,
  NODE_W,
  computeLayout,
  defaultNodeHeight,
  groupRects,
  type Point,
} from '../graph/layout'
import {
  edgeSchemaKey,
  projectKeys,
  readJSON,
  useSetting,
  writeJSON,
} from '../settings'
import {
  maxMetricValue,
  type GraphStartMode,
  type ProcessGraph,
  type ProcessNote,
  type ProcessTransition,
  type StepInfo,
  type TransitionMetric,
} from '../types'
import { GroupBoxNode, type GroupBoxData } from './GroupBoxNode'
import { MARKER_H, MARKER_W, MarkerNode } from './MarkerNode'
import { MetricEdge, type MetricEdgeData } from './MetricEdge'
import { StepNode, type StepNodeData } from './StepNode'

const nodeTypes = { step: StepNode, groupBox: GroupBoxNode, marker: MarkerNode }
const edgeTypes = { metric: MetricEdge }

const GROUP_PREFIX = '__group__'
const collapsedNodeId = (group: string) => `${GROUP_PREFIX}${group}`
const virtualGroupOf = (id: string) =>
  id.startsWith(GROUP_PREFIX) ? id.slice(GROUP_PREFIX.length) : null

export type NodeAction = 'include' | 'exclude'

/** Shared viewport + node positions between the two A/B panels ("valve open"). */
export interface SyncState {
  viewport: Viewport | null
  nodeOverrides: Record<string, Point>
  version: number
}

export function createSyncState(): SyncState {
  return { viewport: null, nodeOverrides: {}, version: 0 }
}

export interface FlowChartProps {
  graph: ProcessGraph
  projectId: string
  /** Included in the persistence key, exactly like the Swift `chartMode`. */
  chartMode: string
  metric: TransitionMetric
  isLoading?: boolean
  /** When provided, viewport and node drags are mirrored to the other panel. */
  syncState?: SyncState | null
  onSyncChange?: () => void
  skipInitialFit?: boolean
  onNodeAction?: (node: string, action: NodeAction) => void
  notes?: ProcessNote[]
  onNodeNote?: (node: string) => void
  onEdgeNote?: (transition: ProcessTransition) => void
  /** Target-process / conformance overlay. */
  normValues?: Record<string, number> | null
  normMetric?: TransitionMetric
  showCompliance?: boolean
  normIsMinimum?: boolean
  onEdgeTap?: (transition: ProcessTransition, screen: { x: number; y: number }) => void
  /** Red note shown in the canvas's top-right corner (e.g. a simulation warning). */
  notice?: string | null
  /** Read-only source (a simulation): hide the interactive filter actions
   *  (Require / Exclude) from the node context menu. */
  readOnly?: boolean
}

interface MenuState {
  kind: 'node' | 'edge'
  node?: string
  transition?: ProcessTransition
  x: number
  y: number
}

function FlowChartInner(props: FlowChartProps) {
  const {
    graph,
    projectId,
    chartMode,
    metric,
    isLoading = false,
    syncState = null,
    onSyncChange,
    skipInitialFit = false,
    onNodeAction,
    notes,
    onNodeNote,
    onEdgeNote,
    normValues = null,
    normMetric = 'Count',
    showCompliance = false,
    normIsMinimum = false,
    onEdgeTap,
  } = props

  const flow = useReactFlow()
  const wrapRef = useRef<HTMLDivElement>(null)

  const [showGrouping] = useSetting<boolean>('processmap.showGrouping')
  const [showNodeDescriptions] = useSetting<boolean>('processmap.showNodeDescriptions')
  const [nodeScale] = useSetting<number>('graph.node.scale')
  const [edgeScale] = useSetting<number>('graph.edge.scale')
  const [groupScale] = useSetting<number>('graph.group.scale')
  const [optimisedLayout] = useSetting<boolean>('graph.optimisedLayout')
  const [colorizeByWeight] = useSetting<boolean>('graph.edge.colorizeByWeight')
  const [graphStartMode] = useSetting<GraphStartMode>('graph.startMode')
  // The schema for the *displayed* metric is reactive so the legend and edges
  // update instantly when it is changed in the colour wizard.
  const [activeSchema] = useSetting<EdgeColorSchema>(edgeSchemaKey(metric))

  const layoutKey = projectKeys.layout(projectId, chartMode)
  const collapsedKey = projectKeys.collapsedGroups(projectId, chartMode)

  const [overrides, setOverrides] = useState<Record<string, Point>>(() =>
    readJSON<Record<string, Point>>(layoutKey, {}),
  )
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [menu, setMenu] = useState<MenuState | null>(null)
  const [descriptionNode, setDescriptionNode] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [showColorWizard, setShowColorWizard] = useState(false)

  const allGroupNames = useMemo(
    () =>
      new Set(
        Object.values(graph.steps)
          .map((s) => s.belongsTo)
          .filter((g): g is string => !!g),
      ),
    [graph.steps],
  )

  // ── Initial collapse state (per project, per graph.startMode) ────────────
  const appliedGroupProject = useRef<string>('')
  useEffect(() => {
    if (allGroupNames.size === 0) return
    if (appliedGroupProject.current === projectId) return
    appliedGroupProject.current = projectId

    if (graphStartMode === 'expanded') setCollapsedGroups(new Set())
    else if (graphStartMode === 'collapsed') setCollapsedGroups(new Set(allGroupNames))
    else {
      const stored = readJSON<string[]>(collapsedKey, [])
      setCollapsedGroups(new Set(stored.filter((g) => allGroupNames.has(g))))
    }
  }, [projectId, graphStartMode, allGroupNames, collapsedKey])

  const toggleGroup = useCallback(
    (group: string) => {
      setCollapsedGroups((prev) => {
        const next = new Set(prev)
        if (next.has(group)) next.delete(group)
        else next.add(group)
        if (graphStartMode === 'persisted') writeJSON(collapsedKey, [...next])
        return next
      })
    },
    [graphStartMode, collapsedKey],
  )

  // ── Collapse resolution (ports resolvedSteps / resolvedTransitions) ──────

  const nodesInGroup = useCallback(
    (group: string) =>
      Object.entries(graph.steps)
        .filter(([, step]) => step.belongsTo === group)
        .map(([name]) => name),
    [graph.steps],
  )

  const resolvedStep = useCallback(
    (step: string) => {
      for (const group of collapsedGroups) {
        if (graph.steps[step]?.belongsTo === group) return collapsedNodeId(group)
      }
      return step
    },
    [collapsedGroups, graph.steps],
  )

  const drawGraph = useMemo<ProcessGraph>(() => {
    if (collapsedGroups.size === 0) return graph

    // Counts summed, times weighted-averaged; intra-group edges dropped.
    const acc = new Map<
      string,
      { from: string; to: string; occ: number; wTime: number; wCount: number }
    >()
    for (const t of graph.transitions) {
      const from = resolvedStep(t.fromStep)
      const to = resolvedStep(t.toStep)
      if (from === to) continue
      const key = `${from}->${to}`
      const entry = acc.get(key) ?? { from, to, occ: 0, wTime: 0, wCount: 0 }
      entry.occ += t.occurrences
      if (t.avgSecs != null) {
        entry.wTime += t.avgSecs * t.occurrences
        entry.wCount += t.occurrences
      }
      acc.set(key, entry)
    }
    const transitions: ProcessTransition[] = [...acc.values()].map((e) => ({
      fromStep: e.from,
      toStep: e.to,
      occurrences: e.occ,
      avgSecs: e.wCount > 0 ? e.wTime / e.wCount : null,
      minSecs: null,
      maxSecs: null,
      stdDevSecs: null,
    }))

    const steps: Record<string, StepInfo> = { ...graph.steps }
    for (const group of collapsedGroups) {
      for (const member of nodesInGroup(group)) delete steps[member]
      steps[collapsedNodeId(group)] = {
        step: group,
        description: '',
        bgColor: 'accentColor',
        fgColor: 'white',
        score: null,
        shape: 'stadium',
        endOfProcess: false,
        belongsTo: null,
        eventTime: null,
      }
    }
    return { steps, transitions }
  }, [graph, collapsedGroups, nodesInGroup, resolvedStep])

  // Node scale grows the node box AND the font together, so text always stays
  // inside; the layout uses the scaled dimensions so nodes never overlap.
  const scale = nodeScale || 1
  const nodeW = Math.round(NODE_W * scale)
  const nodeH = Math.round(defaultNodeHeight(graph) * scale)

  const gLabelScale = groupScale || 1
  const layout = useMemo(
    () => computeLayout(graph, nodeH, optimisedLayout, nodeW, gLabelScale),
    [graph, nodeH, nodeW, optimisedLayout, gLabelScale],
  )

  const effectiveOverrides = syncState ? syncState.nodeOverrides : overrides

  /** Auto-layout ∪ user drags, with collapsed groups folded into a centroid. */
  const positions = useMemo<Record<string, Point>>(() => {
    const base: Record<string, Point> = { ...layout.nodePositions, ...effectiveOverrides }
    if (collapsedGroups.size === 0) return base

    const result = { ...base }
    for (const group of collapsedGroups) {
      const members = nodesInGroup(group)
      const vid = collapsedNodeId(group)
      const hasOverride = result[vid] != null
      const points = members.map((m) => result[m]).filter(Boolean) as Point[]
      for (const m of members) delete result[m]
      if (!hasOverride && points.length > 0) {
        result[vid] = {
          x: points.reduce((s, p) => s + p.x, 0) / points.length,
          y: points.reduce((s, p) => s + p.y, 0) / points.length,
        }
      }
    }
    return result
  }, [layout.nodePositions, effectiveOverrides, collapsedGroups, nodesInGroup])

  // Which node names currently have a position. This set only changes when nodes
  // are added/removed (collapse, project switch) — NOT while dragging — so edges
  // that depend on it stay referentially stable during a drag. ReactFlow re-routes
  // the edges from the live node positions itself, so they still follow the drag.
  const positionedKey = Object.keys(positions).sort().join(' ')
  const positionedIds = useMemo(
    () => new Set(positionedKey ? positionedKey.split(' ') : []),
    [positionedKey],
  )

  // ── Start / end process markers ─────────────────────────────────────────

  const { startNodes, endNodes } = useMemo(() => {
    const real = drawGraph.transitions.filter((t) => t.fromStep !== t.toStep)
    const targets = new Set(real.map((t) => t.toStep))
    const sources = new Set(real.map((t) => t.fromStep))
    const names = Object.keys(drawGraph.steps)
    return {
      startNodes: names.filter((n) => !targets.has(n)),
      endNodes: names.filter((n) => !sources.has(n)),
    }
  }, [drawGraph])

  const boxes = useMemo(
    () =>
      showGrouping
        ? groupRects(graph, positions, collapsedGroups, nodeH, collapsedNodeId, nodeW, gLabelScale)
        : [],
    [showGrouping, graph, positions, collapsedGroups, nodeH, nodeW, gLabelScale],
  )

  // ── Note lookup ─────────────────────────────────────────────────────────

  const { noteNodes, noteEdges, noteCounts } = useMemo(() => {
    const nodesWithNotes = new Set<string>()
    const edgesWithNotes = new Set<string>()
    const counts = new Map<string, number>() // "node:<name>" / "edge:<from>-><to>" → count
    for (const note of notes ?? []) {
      let key: string | null = null
      if (note.target.type === 'edge') {
        const e = `${note.target.from}->${note.target.to}`
        edgesWithNotes.add(e)
        key = `edge:${e}`
      } else if (note.target.value) {
        nodesWithNotes.add(note.target.value)
        key = `node:${note.target.value}`
      }
      if (key) counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return { noteNodes: nodesWithNotes, noteEdges: edgesWithNotes, noteCounts: counts }
  }, [notes])

  // ── ReactFlow nodes ─────────────────────────────────────────────────────
  //
  // Node objects are memoised by a content signature: a node whose position and
  // data are unchanged keeps its exact object reference across re-derivations, so
  // ReactFlow (and the memoised node components) skip re-rendering it. Without
  // this, every re-derive minted all-new node objects and ReactFlow re-rendered
  // *all* nodes on every pointermove of a single-node drag.
  const nodeCache = useRef(new Map<string, { sig: string; node: Node }>())
  // Stable per-object id for StepInfo values, so the signature changes when the
  // underlying step object is replaced (a structural change) but not on a drag.
  const stepIds = useRef({ map: new WeakMap<object, number>(), seq: 0 })
  const stepIdOf = useCallback((s: object) => {
    const store = stepIds.current
    let id = store.map.get(s)
    if (id == null) {
      id = ++store.seq
      store.map.set(s, id)
    }
    return id
  }, [])

  const rfNodes = useMemo<Node[]>(() => {
    const cache = nodeCache.current
    const seen = new Set<string>()
    const result: Node[] = []
    const emit = (id: string, sig: string, build: () => Node) => {
      seen.add(id)
      const hit = cache.get(id)
      if (hit && hit.sig === sig) {
        result.push(hit.node)
        return
      }
      const node = build()
      cache.set(id, { sig, node })
      result.push(node)
    }

    for (const { name, rect } of boxes) {
      const id = `box:${name}`
      const color = groupColorFor(name)
      const collapsed = collapsedGroups.has(name)
      emit(
        id,
        `box|${rect.x}|${rect.y}|${rect.width}|${rect.height}|${color}|${collapsed ? 1 : 0}|${groupScale}`,
        () => ({
          id,
          type: 'groupBox',
          position: { x: rect.x, y: rect.y },
          // Declared size so ReactFlow keeps the node dimensioned AND keeps its
          // handle bounds when it rebuilds the internal node on a drag (new object
          // ref). `measured` makes adoptUserNodes/parseHandles preserve the existing
          // handleBounds; without it the box + members flip to visibility:hidden and
          // every connected edge drops out (isNodeInitialized → false) for the whole
          // drag, since a position-only change never re-fires the ResizeObserver.
          measured: { width: rect.width, height: rect.height },
          initialWidth: rect.width,
          initialHeight: rect.height,
          data: {
            group: name,
            width: rect.width,
            height: rect.height,
            color,
            collapsed,
            scale: groupScale || 1,
            onToggle: toggleGroup,
          } satisfies GroupBoxData,
          draggable: true,
          selectable: false,
          zIndex: 0,
        }),
      )
    }

    for (const [name, step] of Object.entries(drawGraph.steps)) {
      const pos = positions[name]
      if (!pos) continue
      const group = virtualGroupOf(name)
      const left = { x: pos.x - nodeW / 2, y: pos.y - nodeH / 2 }
      const memberCount = group ? nodesInGroup(group).length : 0
      const groupCol = group ? groupColorFor(group) : ''
      const hasNote = noteNodes.has(name)
      emit(
        name,
        `step|${left.x}|${left.y}|${nodeW}|${nodeH}|${scale}|${showNodeDescriptions ? 1 : 0}|${
          hasNote ? 1 : 0
        }|${group ?? ''}|${memberCount}|${groupCol}|${stepIdOf(step)}`,
        () => ({
          id: name,
          type: 'step',
          position: left,
          // Declared size — see the group box note above: keeps the node visible
          // and its edges attached when its object is rebuilt mid-drag.
          measured: { width: nodeW, height: nodeH },
          initialWidth: nodeW,
          initialHeight: nodeH,
          data: {
            name: group ?? name,
            step,
            nodeW,
            nodeH,
            scale,
            showDescription: showNodeDescriptions,
            groupProxy: group
              ? { group, memberCount, color: groupCol }
              : null,
            hasNote,
          } satisfies StepNodeData,
          draggable: true,
          zIndex: 2,
        }),
      )
    }

    // Markers sit above / below the node, or clear of the group box when the
    // node belongs to one — matching the Swift `tipY` / `baseY` logic.
    const boxByName = new Map(boxes.map((b) => [b.name, b.rect]))
    const groupOf = (name: string) =>
      virtualGroupOf(name) ?? graph.steps[name]?.belongsTo ?? null

    for (const name of startNodes) {
      const pos = positions[name]
      if (!pos) continue
      const box = showGrouping ? boxByName.get(groupOf(name) ?? '') : undefined
      const tipY = box ? box.y - 16 : pos.y - nodeH / 2 - 6
      const p = { x: pos.x - MARKER_W / 2, y: tipY - MARKER_H }
      emit(`start:${name}`, `start|${p.x}|${p.y}`, () => ({
        id: `start:${name}`,
        type: 'marker',
        position: p,
        measured: { width: MARKER_W, height: MARKER_H },
        initialWidth: MARKER_W,
        initialHeight: MARKER_H,
        data: { kind: 'start' },
        draggable: false,
        selectable: false,
        zIndex: 1,
      }))
    }
    for (const name of endNodes) {
      const pos = positions[name]
      if (!pos) continue
      const box = showGrouping ? boxByName.get(groupOf(name) ?? '') : undefined
      const baseY = box ? box.y + box.height + 8 : pos.y + nodeH / 2 + 8
      const p = { x: pos.x - MARKER_W / 2, y: baseY }
      emit(`end:${name}`, `end|${p.x}|${p.y}`, () => ({
        id: `end:${name}`,
        type: 'marker',
        position: p,
        measured: { width: MARKER_W, height: MARKER_H },
        initialWidth: MARKER_W,
        initialHeight: MARKER_H,
        data: { kind: 'end' },
        draggable: false,
        selectable: false,
        zIndex: 1,
      }))
    }

    // Drop cache entries for nodes that no longer exist (collapse, project switch).
    for (const key of cache.keys()) if (!seen.has(key)) cache.delete(key)

    return result
  }, [
    boxes,
    collapsedGroups,
    drawGraph.steps,
    endNodes,
    graph.steps,
    groupScale,
    nodeH,
    nodeW,
    scale,
    nodesInGroup,
    noteNodes,
    positions,
    showGrouping,
    showNodeDescriptions,
    startNodes,
    stepIdOf,
    toggleGroup,
  ])

  // ── ReactFlow edges ─────────────────────────────────────────────────────

  const rfEdges = useMemo<Edge[]>(() => {
    const showNorms = normValues != null
    const maxValue = showNorms
      ? maxMetricValue(drawGraph, normMetric)
      : maxMetricValue(drawGraph, metric)
    const schema = activeSchema

    const outgoing = new Map<string, number>()
    for (const t of drawGraph.transitions) {
      outgoing.set(t.fromStep, (outgoing.get(t.fromStep) ?? 0) + t.occurrences)
    }

    return drawGraph.transitions
      .filter((t) => positionedIds.has(t.fromStep) && positionedIds.has(t.toStep))
      .map((t) => {
        const id = `${t.fromStep}->${t.toStep}`
        return {
          id,
          source: t.fromStep,
          target: t.toStep,
          type: 'metric',
          zIndex: 1,
          data: {
            transition: t,
            metric,
            maxValue,
            colorize: colorizeByWeight,
            schema,
            normValue: normValues?.[id] ?? null,
            normMetric,
            showNorms,
            showCompliance,
            normIsMinimum,
            outgoingTotal: outgoing.get(t.fromStep) ?? 0,
            hasNote: noteEdges.has(id),
            nodeH,
            edgeScale: edgeScale || 1,
            onEdgeClick:
              onEdgeTap ??
              (onEdgeNote
                ? (transition, screen) =>
                    setMenu({
                      kind: 'edge',
                      transition,
                      x: screen.x,
                      y: screen.y,
                    })
                : undefined),
          } satisfies MetricEdgeData,
        } satisfies Edge
      })
  }, [
    activeSchema,
    colorizeByWeight,
    drawGraph,
    edgeScale,
    metric,
    nodeH,
    normIsMinimum,
    normMetric,
    normValues,
    noteEdges,
    onEdgeNote,
    onEdgeTap,
    positionedIds,
    showCompliance,
  ])

  // ── Dragging ────────────────────────────────────────────────────────────

  // Per-group drag snapshot: the box's start position plus each member's start
  // position, captured once when a group drag begins (see onNodesChange).
  const dragOrigins = useRef<
    Record<string, { box: Point; members: Record<string, Point> }>
  >({})

  const commitOverrides = useCallback(
    (next: Record<string, Point>, persist = true) => {
      if (syncState) {
        syncState.nodeOverrides = next
        syncState.version += 1
        onSyncChange?.()
      }
      setOverrides(next)
      if (persist) writeJSON(layoutKey, next)
    },
    [layoutKey, onSyncChange, syncState],
  )

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let next: Record<string, Point> | null = null
      let dragEnded = false

      for (const change of changes) {
        if (change.type !== 'position' || !change.position) continue
        // `dragging` is true for every intermediate move and false on the final
        // change of a gesture (and undefined for programmatic moves) — either way
        // that is when the result should be written through to storage.
        if (change.dragging !== true) dragEnded = true
        const id = change.id

        if (id.startsWith('box:')) {
          // Dragging the box moves every member (or the proxy when collapsed).
          // The member origins are snapshotted once at drag start; applying the
          // cumulative pointer delta to those fixed origins (never to the live,
          // already-moved positions) is what keeps the group from compounding
          // its own movement and flying off-screen.
          const group = id.slice(4)
          const box = boxes.find((b) => b.name === group)
          if (!box) continue
          let snapshot = dragOrigins.current[id]
          if (!snapshot) {
            const members = collapsedGroups.has(group)
              ? [collapsedNodeId(group)]
              : nodesInGroup(group)
            const memberOrigins: Record<string, Point> = {}
            for (const member of members) {
              const base = positions[member]
              if (base) memberOrigins[member] = base
            }
            snapshot = { box: { x: box.rect.x, y: box.rect.y }, members: memberOrigins }
            dragOrigins.current[id] = snapshot
          }
          const dx = change.position.x - snapshot.box.x
          const dy = change.position.y - snapshot.box.y
          next ??= { ...effectiveOverrides }
          for (const [member, base] of Object.entries(snapshot.members)) {
            next[member] = snap({ x: base.x + dx, y: base.y + dy })
          }
          if (!change.dragging) delete dragOrigins.current[id]
          continue
        }

        if (id.startsWith('start:') || id.startsWith('end:')) continue

        next ??= { ...effectiveOverrides }
        next[id] = snap({
          x: change.position.x + nodeW / 2,
          y: change.position.y + nodeH / 2,
        })
      }

      // Persist to storage only when the gesture ends (change.dragging === false),
      // never on every intermediate move — the per-move localStorage write was the
      // main source of drag jank. In-memory overrides still update every move so
      // the node tracks the cursor smoothly.
      if (next) commitOverrides(next, dragEnded)
    },
    [
      boxes,
      collapsedGroups,
      commitOverrides,
      effectiveOverrides,
      nodeH,
      nodeW,
      nodesInGroup,
      positions,
    ],
  )

  // ── Viewport: initial fit + optional A/B sync ───────────────────────────

  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current || rfNodes.length === 0) return
    fitted.current = true
    if (skipInitialFit && syncState?.viewport) {
      flow.setViewport(syncState.viewport)
    } else {
      window.requestAnimationFrame(() => {
        flow.fitView({ padding: 0.12, duration: 0 })
        setZoom(flow.getZoom())
      })
    }
  }, [flow, rfNodes.length, skipInitialFit, syncState])

  // Re-fit when a new project is opened.
  useEffect(() => {
    fitted.current = false
  }, [projectId])

  const syncVersion = syncState?.version ?? 0
  useEffect(() => {
    if (!syncState?.viewport) return
    const current = flow.getViewport()
    const v = syncState.viewport
    if (
      Math.abs(current.x - v.x) < 0.5 &&
      Math.abs(current.y - v.y) < 0.5 &&
      Math.abs(current.zoom - v.zoom) < 0.001
    ) {
      return
    }
    flow.setViewport(v)
    setZoom(v.zoom)
  }, [flow, syncState, syncVersion])

  const onMove = useCallback(
    (_: unknown, viewport: Viewport) => {
      setZoom(viewport.zoom)
      if (syncState) {
        syncState.viewport = viewport
        syncState.version += 1
        onSyncChange?.()
      }
    },
    [onSyncChange, syncState],
  )

  const resetLayout = useCallback(() => {
    commitOverrides({})
    window.requestAnimationFrame(() => {
      flow.fitView({ padding: 0.12, duration: 350 })
      setZoom(flow.getZoom())
    })
  }, [commitOverrides, flow])

  const zoomBy = useCallback(
    (factor: number) => {
      const next = Math.max(0.15, Math.min(5, flow.getZoom() * factor))
      flow.zoomTo(next, { duration: 200 })
      setZoom(next)
    },
    [flow],
  )

  // ── Colour-scale legend ─────────────────────────────────────────────────

  const gradient = EDGE_SCHEMA_GRADIENTS[activeSchema]
  const scaleStyle: CSSProperties = gradient
    ? {
        background: `linear-gradient(90deg, ${gradient.low}, ${interpolate(
          gradient.low,
          gradient.high,
          0.5,
        )}, ${gradient.high})`,
      }
    : { background: 'rgba(120,120,128,0.25)' }

  const menuNodeStep = menu?.node ? graph.steps[menu.node] : undefined
  const menuDescription = menuNodeStep?.description ?? ''
  const menuHasDescription =
    showNodeDescriptions &&
    menuDescription.length > 0 &&
    menuDescription !== menu?.node

  return (
    <div className="flow-wrap" ref={wrapRef}>
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onMove={onMove}
        onNodeClick={(event, node) => {
          if (!onNodeAction) return
          if (node.id.startsWith('box:') || virtualGroupOf(node.id)) return
          setMenu({ kind: 'node', node: node.id, x: event.clientX, y: event.clientY })
        }}
        onPaneClick={() => {
          setMenu(null)
          setDescriptionNode(null)
        }}
        onDoubleClick={() => flow.fitView({ padding: 0.12, duration: 350 })}
        minZoom={0.15}
        maxZoom={5}
        snapToGrid
        snapGrid={[GRID_SIZE, GRID_SIZE]}
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: false }}
        defaultEdgeOptions={{ type: 'metric' }}
      >
        <Background variant={BackgroundVariant.Dots} gap={GRID_SIZE} size={1} />
      </ReactFlow>

      {isLoading && (
        <div className="loading-pill row">
          <span className="spinner" /> Loading…
        </div>
      )}

      {props.notice && (
        <div className="flow-notice" role="status">
          {props.notice}
        </div>
      )}

      {collapsedGroups.size > 0 && (
        <div
          style={{
            position: 'absolute',
            bottom: 12,
            left: '50%',
            transform: 'translateX(-50%)',
            fontSize: 11,
            color: 'var(--secondary)',
            pointerEvents: 'none',
          }}
        >
          Collapsed groups: connection counts summed · times weighted-averaged
        </div>
      )}

      <div className="flow-overlay">
        {colorizeByWeight && (
          <button
            className="color-scale color-scale-btn"
            onClick={() => setShowColorWizard(true)}
            title="Configure edge colour schema per metric"
            aria-label="Configure edge colour schema"
          >
            <div className="row t-caption2 fg-secondary" style={{ gap: 4 }}>
              {metric}
              <span style={{ marginLeft: 'auto', opacity: 0.6 }}>⚙</span>
            </div>
            <div className="bar" style={scaleStyle} />
            {gradient ? (
              <div className="ends">
                <span>Low</span>
                <span>High</span>
              </div>
            ) : (
              <div className="ends">
                <span>No color scale</span>
              </div>
            )}
          </button>
        )}

        <div className="zoom-controls">
          <button onClick={() => zoomBy(1 / 1.3)} title="Zoom out">
            −
          </button>
          <span className="zoom-value">{Math.round(zoom * 100)}%</span>
          <button onClick={() => zoomBy(1.3)} title="Zoom in">
            +
          </button>
          <button
            onClick={() => flow.fitView({ padding: 0.12, duration: 350 })}
            title="Fit to view"
          >
            ⤢
          </button>
          <span className="sep" />
          <button onClick={resetLayout} title="Reset node layout">
            ↺
          </button>
          {showGrouping && allGroupNames.size > 0 && (
            <>
              <span className="sep" />
              <button
                onClick={() =>
                  setCollapsedGroups((prev) =>
                    prev.size === allGroupNames.size ? new Set() : new Set(allGroupNames),
                  )
                }
                title={
                  collapsedGroups.size === allGroupNames.size
                    ? 'Expand all groups'
                    : 'Collapse all groups'
                }
              >
                {collapsedGroups.size === allGroupNames.size ? '⤢' : '⤡'}
              </button>
            </>
          )}
        </div>
      </div>

      {menu?.kind === 'node' && menu.node && onNodeAction && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 199 }}
            onClick={() => setMenu(null)}
          />
          <div
            className="popover"
            style={{ left: clampX(menu.x), top: clampY(menu.y + 12) }}
          >
            <div className="p-title">{menu.node}</div>
            {!props.readOnly && (
              <>
                <button
                  className="p-item"
                  onClick={() => {
                    onNodeAction(menu.node as string, 'include')
                    setMenu(null)
                  }}
                >
                  ✓ Require in journeys
                </button>
                <button
                  className="p-item fg-red"
                  onClick={() => {
                    onNodeAction(menu.node as string, 'exclude')
                    setMenu(null)
                  }}
                >
                  ⊖ Exclude from journeys
                </button>
              </>
            )}
            {menuHasDescription && (
              <button
                className="p-item"
                onClick={() => {
                  setDescriptionNode(menu.node as string)
                  setMenu(null)
                }}
              >
                ≡ Show description
              </button>
            )}
            {onNodeNote && (
              <button
                className="p-item"
                style={{ color: 'var(--yellow)' }}
                onClick={() => {
                  onNodeNote(menu.node as string)
                  setMenu(null)
                }}
              >
                ✎ Show Notes ({noteCounts.get(`node:${menu.node}`) ?? 0})
              </button>
            )}
          </div>
        </>
      )}

      {menu?.kind === 'edge' && menu.transition && onEdgeNote && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 199 }}
            onClick={() => setMenu(null)}
          />
          <div
            className="popover"
            style={{ left: clampX(menu.x), top: clampY(menu.y + 12) }}
          >
            <div className="p-title">
              {menu.transition.fromStep} → {menu.transition.toStep}
            </div>
            <button
              className="p-item"
              style={{ color: 'var(--yellow)' }}
              onClick={() => {
                onEdgeNote(menu.transition as ProcessTransition)
                setMenu(null)
              }}
            >
              ✎ Show Notes (
              {noteCounts.get(
                `edge:${menu.transition.fromStep}->${menu.transition.toStep}`,
              ) ?? 0}
              )
            </button>
          </div>
        </>
      )}

      {descriptionNode && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 199 }}
            onClick={() => setDescriptionNode(null)}
          />
          <div
            className="popover"
            style={{
              left: '50%',
              top: '50%',
              transform: 'translate(-50%, -50%)',
              width: 260,
              padding: 14,
            }}
          >
            <div className="t-caption fg-secondary" style={{ fontWeight: 600 }}>
              {descriptionNode}
            </div>
            <hr className="divider" style={{ margin: '8px 0' }} />
            <div className="t-callout" style={{ whiteSpace: 'pre-wrap' }}>
              {graph.steps[descriptionNode]?.description}
            </div>
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
              <button className="btn small" onClick={() => setDescriptionNode(null)}>
                Done
              </button>
            </div>
          </div>
        </>
      )}

      {showColorWizard && (
        <EdgeColorWizard onClose={() => setShowColorWizard(false)} />
      )}
    </div>
  )
}

function snap(p: Point): Point {
  return {
    x: Math.round(p.x / GRID_SIZE) * GRID_SIZE,
    y: Math.round(p.y / GRID_SIZE) * GRID_SIZE,
  }
}

function clampX(x: number): number {
  return Math.max(120, Math.min(window.innerWidth - 230, x))
}

function clampY(y: number): number {
  return Math.max(60, Math.min(window.innerHeight - 200, y))
}

export function FlowChart(props: FlowChartProps) {
  return (
    <ReactFlowProvider>
      <FlowChartInner {...props} />
    </ReactFlowProvider>
  )
}
