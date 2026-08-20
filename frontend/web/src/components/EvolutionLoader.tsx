/** The "AI supported Reporting" easter egg: the March of Progress, animated.
 *
 *  ONE figure continuously morphs through the stages of evolution — crawling,
 *  knuckle-walking, hunched, upright — ending as the final stage of evolution:
 *  a human reading a glowing smartphone. Then it fluidly devolves back to the
 *  crawl and the cycle repeats.
 *
 *  The figure is deliberately more body than stick: the torso is a filled,
 *  tapered shape built each frame around a three-point spine (hip → belly →
 *  shoulder) with rounded caps, plus a neck and heavier legs. Every stage poses
 *  the same skeleton, so eased linear interpolation between poses reads as a
 *  smooth morph. Driven by requestAnimationFrame (CSS cannot animate SVG path
 *  coordinates cross-browser); theme-aware via currentColor; honours
 *  prefers-reduced-motion by showing the final pose statically. */

import { useEffect, useRef } from 'react'

type Pt = readonly [number, number]
interface Pose {
  head: Pt
  /** hip → belly → shoulder */
  spine: readonly [Pt, Pt, Pt]
  armF: readonly Pt[]
  armB: readonly Pt[]
  legF: readonly Pt[]
  legB: readonly Pt[]
}

/* STAGES-BEGIN */
const STAGES: readonly Pose[] = [
  {
    // 1 — crawling on all fours (back gently arched)
    head: [82, 62],
    spine: [[40, 66], [57, 60], [72, 62]],
    armF: [[70, 63], [74, 72], [76, 84]],
    armB: [[68, 63], [64, 73], [62, 84]],
    legF: [[40, 66], [46, 75], [48, 84]],
    legB: [[40, 66], [34, 74], [32, 84]],
  },
  {
    // 2 — knuckle-walking (humped back)
    head: [72, 43],
    spine: [[44, 70], [57, 56], [66, 48]],
    armF: [[64, 50], [72, 66], [76, 84]],
    armB: [[62, 52], [66, 68], [64, 84]],
    legF: [[44, 70], [50, 77], [52, 84]],
    legB: [[44, 70], [38, 76], [36, 84]],
  },
  {
    // 3 — hunched, almost upright (rounded back)
    head: [66, 33],
    spine: [[52, 68], [60, 53], [62, 40]],
    armF: [[60, 46], [66, 58], [68, 68]],
    armB: [[59, 48], [62, 60], [60, 70]],
    legF: [[52, 68], [58, 76], [58, 84]],
    legB: [[52, 68], [48, 76], [46, 84]],
  },
  {
    // 4 — upright, mid-stride (proud chest)
    head: [60, 21],
    spine: [[60, 56], [61, 43], [60, 30]],
    armF: [[60, 36], [66, 44], [70, 50]],
    armB: [[60, 36], [54, 44], [50, 50]],
    legF: [[60, 56], [68, 68], [72, 82]],
    legB: [[60, 56], [54, 70], [50, 84]],
  },
  {
    // 5 — the final stage: standing, phone raised, head bowed to the screen
    head: [62, 21],
    spine: [[60, 56], [61, 43], [61, 30]],
    armF: [[61, 37], [69, 42], [71, 32]],
    armB: [[61, 37], [55, 46], [52, 52]],
    legF: [[60, 56], [63, 70], [64, 84]],
    legB: [[60, 56], [57, 70], [56, 84]],
  },
]
/* STAGES-END */

/** Torso half-widths along the spine: hip, belly, shoulder. */
const TORSO_W: readonly [number, number, number] = [6.0, 7.2, 6.4]

/** Shoe profile in ankle-local coordinates (origin = ankle, toe pointing right). */
const SHOE_D =
  'M-3 2.3 L7.7 2.3 Q9 2.3 8.6 0.9 Q8 -0.7 5.9 -1.1 L0.8 -2 Q-2.5 -2.6 -3 -0.4 Z'

const HOLD_MS = 420 // pose rests briefly so each stage registers…
const MORPH_MS = 850 // …then flows into the next
const SEG_MS = HOLD_MS + MORPH_MS
const CYCLE_MS = SEG_MS * STAGES.length // last segment morphs 5 → 1 (the loop)

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const smooth = (t: number) => t * t * (3 - 2 * t) // smoothstep easing

function mixPts(a: readonly Pt[], b: readonly Pt[], t: number): [number, number][] {
  return a.map((p, i) => [lerp(p[0], b[i][0], t), lerp(p[1], b[i][1], t)])
}

const polyline = (pts: readonly (readonly number[])[]) =>
  pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0]} ${p[1]}`).join('')

/** Filled, tapered torso outline around the spine (left side out, right side back). */
function torsoOutline(spine: readonly (readonly number[])[]): string {
  const left: number[][] = []
  const right: number[][] = []
  for (let i = 0; i < spine.length; i++) {
    // Central-difference tangent, then its normal, scaled by the local width.
    const p0 = spine[Math.max(0, i - 1)]
    const p1 = spine[Math.min(spine.length - 1, i + 1)]
    const dx = p1[0] - p0[0]
    const dy = p1[1] - p0[1]
    const len = Math.hypot(dx, dy) || 1
    const nx = (-dy / len) * TORSO_W[i]
    const ny = (dx / len) * TORSO_W[i]
    left.push([spine[i][0] + nx, spine[i][1] + ny])
    right.push([spine[i][0] - nx, spine[i][1] - ny])
  }
  return polyline(left) + right.reverse().map((p) => `L${p[0]} ${p[1]}`).join('') + 'Z'
}

export function EvolutionLoader() {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const el = (name: string) => svg.querySelector<SVGElement>(`[data-part="${name}"]`)
    const parts = {
      head: el('head'),
      torso: el('torso'),
      hipCap: el('hipCap'),
      shoulderCap: el('shoulderCap'),
      neck: el('neck'),
      armF: el('armF'),
      armB: el('armB'),
      legF: el('legF'),
      legB: el('legB'),
      shoeF: el('shoeF'),
      shoeB: el('shoeB'),
      phone: el('phone'),
    }
    if (Object.values(parts).some((p) => !p)) return

    function apply(i: number, j: number, tRaw: number, phoneAlpha: number) {
      const t = smooth(tRaw)
      const a = STAGES[i]
      const b = STAGES[j]

      const spine = mixPts(a.spine, b.spine, t)
      parts.torso!.setAttribute('d', torsoOutline(spine))
      const setCap = (cap: SVGElement, p: number[], r: number) => {
        cap.setAttribute('cx', String(p[0]))
        cap.setAttribute('cy', String(p[1]))
        cap.setAttribute('r', String(r))
      }
      setCap(parts.hipCap!, spine[0], TORSO_W[0])
      setCap(parts.shoulderCap!, spine[2], TORSO_W[2])

      const head: number[] = [lerp(a.head[0], b.head[0], t), lerp(a.head[1], b.head[1], t)]
      parts.head!.setAttribute('cx', String(head[0]))
      parts.head!.setAttribute('cy', String(head[1]))
      parts.neck!.setAttribute('d', `M${spine[2][0]} ${spine[2][1]}L${head[0]} ${head[1]}`)

      for (const key of ['armF', 'armB', 'legF', 'legB'] as const) {
        parts[key]!.setAttribute('d', polyline(mixPts(a[key], b[key], t)))
      }
      // Shoes ride the ankles (last leg point) — yes, the ape wears them too.
      const ankleF = mixPts(a.legF, b.legF, t)[2]
      const ankleB = mixPts(a.legB, b.legB, t)[2]
      parts.shoeF!.setAttribute('transform', `translate(${ankleF[0]} ${ankleF[1]})`)
      parts.shoeB!.setAttribute('transform', `translate(${ankleB[0]} ${ankleB[1]})`)
      // The phone rides the front hand (last armF point).
      const hand = mixPts(a.armF, b.armF, t)[2]
      parts.phone!.setAttribute('transform', `translate(${hand[0]} ${hand[1]}) rotate(-14)`)
      parts.phone!.setAttribute('opacity', String(phoneAlpha))
    }

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      apply(STAGES.length - 1, STAGES.length - 1, 0, 1)
      return
    }

    let raf = 0
    const t0 = performance.now()
    const last = STAGES.length - 1

    const tick = (now: number) => {
      const cycle = (now - t0) % CYCLE_MS
      const seg = Math.floor(cycle / SEG_MS) // seg k morphs stage k → k+1 (wrapping)
      const within = cycle - seg * SEG_MS
      const t = within < HOLD_MS ? 0 : (within - HOLD_MS) / MORPH_MS
      const next = (seg + 1) % STAGES.length
      // Phone: fades in while morphing into the last stage, shows during its
      // hold, fades out while devolving back to the crawl.
      let phoneAlpha = 0
      if (next === last) phoneAlpha = t
      else if (seg === last) phoneAlpha = 1 - t
      apply(seg, next, t, phoneAlpha)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <svg
      ref={svgRef}
      className="evo"
      viewBox="0 0 120 92"
      role="img"
      aria-label="Evolution from crawling to the smartphone — the report is being generated"
    >
      <line className="evo-ground" x1="6" y1="84" x2="114" y2="84" />
      <g className="evo-fig">
        {/* limbs behind the body */}
        <path data-part="armB" className="evo-arm evo-back" />
        <path data-part="legB" className="evo-leg evo-back" />
        <path data-part="shoeB" className="evo-back" d={SHOE_D} fill="currentColor" stroke="none" />
        {/* the body: filled tapered torso with rounded hip/shoulder caps + neck */}
        <path data-part="torso" fill="currentColor" stroke="none" />
        <circle data-part="hipCap" fill="currentColor" stroke="none" />
        <circle data-part="shoulderCap" fill="currentColor" stroke="none" />
        <path data-part="neck" className="evo-neck" />
        <circle data-part="head" r="7.4" fill="currentColor" stroke="none" />
        {/* limbs in front of the body */}
        <path data-part="legF" className="evo-leg" />
        <path data-part="shoeF" d={SHOE_D} fill="currentColor" stroke="none" />
        <path data-part="armF" className="evo-arm" />
        {/* the smartphone, anchored to the front hand */}
        <g data-part="phone" opacity="0">
          <rect x="-2.5" y="-11" width="8" height="14" rx="1.8" fill="currentColor" stroke="none" />
          <rect className="evo-screen" x="-1" y="-9" width="5" height="9" rx="0.9" stroke="none" />
        </g>
      </g>
    </svg>
  )
}
