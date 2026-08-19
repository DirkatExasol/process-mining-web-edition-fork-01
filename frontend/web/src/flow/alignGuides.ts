/** Smart alignment guides for dragging steps / groups on the flowchart.
 *
 *  While a node or group box is dragged we compare its six reference edges (left / centre-x
 *  / right, top / centre-y / bottom) against the same edges of every other node and group in
 *  the vicinity. Any pair within `threshold` flow-pixels yields a guide line, and the closest
 *  match per axis gives a snap offset so the dragged item clicks into alignment. */

export interface Bounds {
  left: number
  cx: number
  right: number
  top: number
  cy: number
  bottom: number
}

export interface VLine {
  x: number
  y1: number
  y2: number
}
export interface HLine {
  y: number
  x1: number
  x2: number
}

export interface Guides {
  vertical: VLine[]
  horizontal: HLine[]
  /** Offset to add to the moving item so its nearest edge lands exactly on a target edge. */
  snapDx: number
  snapDy: number
}

export function boundsFromCenter(cx: number, cy: number, w: number, h: number): Bounds {
  const hw = w / 2
  const hh = h / 2
  return { left: cx - hw, cx, right: cx + hw, top: cy - hh, cy, bottom: cy + hh }
}

export function boundsFromRect(x: number, y: number, w: number, h: number): Bounds {
  return { left: x, cx: x + w / 2, right: x + w, top: y, cy: y + h / 2, bottom: y + h }
}

const EMPTY: Guides = { vertical: [], horizontal: [], snapDx: 0, snapDy: 0 }

/** Guide lines + snap offsets for a moving item against static targets. */
export function computeGuides(moving: Bounds, targets: Bounds[], threshold = 6): Guides {
  if (targets.length === 0) return EMPTY
  const movingX: number[] = [moving.left, moving.cx, moving.right]
  const movingY: number[] = [moving.top, moving.cy, moving.bottom]

  // Merge vertical lines that share an x (from several aligned targets), extending the span.
  const vMap = new Map<number, { y1: number; y2: number }>()
  const hMap = new Map<number, { x1: number; x2: number }>()
  let snapDx = 0
  let bestDx = Infinity
  let snapDy = 0
  let bestDy = Infinity

  for (const t of targets) {
    for (const tv of [t.left, t.cx, t.right]) {
      for (const mv of movingX) {
        const d = tv - mv
        if (Math.abs(d) > threshold) continue
        const key = Math.round(tv * 10) / 10
        const prev = vMap.get(key)
        const y1 = Math.min(moving.top, t.top)
        const y2 = Math.max(moving.bottom, t.bottom)
        vMap.set(key, prev ? { y1: Math.min(prev.y1, y1), y2: Math.max(prev.y2, y2) } : { y1, y2 })
        if (Math.abs(d) < bestDx) {
          bestDx = Math.abs(d)
          snapDx = d
        }
      }
    }
    for (const tv of [t.top, t.cy, t.bottom]) {
      for (const mv of movingY) {
        const d = tv - mv
        if (Math.abs(d) > threshold) continue
        const key = Math.round(tv * 10) / 10
        const prev = hMap.get(key)
        const x1 = Math.min(moving.left, t.left)
        const x2 = Math.max(moving.right, t.right)
        hMap.set(key, prev ? { x1: Math.min(prev.x1, x1), x2: Math.max(prev.x2, x2) } : { x1, x2 })
        if (Math.abs(d) < bestDy) {
          bestDy = Math.abs(d)
          snapDy = d
        }
      }
    }
  }

  return {
    vertical: [...vMap].map(([x, s]) => ({ x, y1: s.y1, y2: s.y2 })),
    horizontal: [...hMap].map(([y, s]) => ({ y, x1: s.x1, x2: s.x2 })),
    snapDx: bestDx <= threshold ? snapDx : 0,
    snapDy: bestDy <= threshold ? snapDy : 0,
  }
}
