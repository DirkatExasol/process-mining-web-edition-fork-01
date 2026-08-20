/** The "AI supported Reporting" easter egg: the March of Progress, animated.
 *
 *  ONE figure continuously morphs through the stages of evolution — crawling,
 *  knuckle-walking, hunched, upright — ending as the final stage of evolution:
 *  a human reading a glowing smartphone. Then it fluidly devolves back to the
 *  crawl and the cycle repeats.
 *
 *  Every stage poses the same skeleton (head, torso, two 3-point arms, two
 *  3-point legs), so a plain eased linear interpolation between consecutive
 *  poses reads as a smooth morph. Driven by requestAnimationFrame (CSS cannot
 *  animate SVG path coordinates cross-browser); theme-aware via currentColor;
 *  honours prefers-reduced-motion by showing the final pose statically. */

import { useEffect, useRef } from 'react'

type Pt = readonly [number, number]
interface Pose {
  head: Pt
  torso: readonly Pt[]
  armF: readonly Pt[]
  armB: readonly Pt[]
  legF: readonly Pt[]
  legB: readonly Pt[]
}

/* STAGES-BEGIN */
const STAGES: readonly Pose[] = [
  {
    // 1 — crawling on all fours
    head: [82, 63],
    torso: [[40, 66], [72, 62]],
    armF: [[70, 63], [74, 72], [76, 84]],
    armB: [[68, 63], [64, 73], [62, 84]],
    legF: [[40, 66], [46, 75], [48, 84]],
    legB: [[40, 66], [34, 74], [32, 84]],
  },
  {
    // 2 — knuckle-walking
    head: [72, 44],
    torso: [[44, 70], [66, 48]],
    armF: [[64, 50], [72, 66], [76, 84]],
    armB: [[62, 52], [66, 68], [64, 84]],
    legF: [[44, 70], [50, 77], [52, 84]],
    legB: [[44, 70], [38, 76], [36, 84]],
  },
  {
    // 3 — hunched, almost upright
    head: [66, 34],
    torso: [[52, 68], [62, 40]],
    armF: [[60, 46], [66, 58], [68, 68]],
    armB: [[59, 48], [62, 60], [60, 70]],
    legF: [[52, 68], [58, 76], [58, 84]],
    legB: [[52, 68], [48, 76], [46, 84]],
  },
  {
    // 4 — upright, mid-stride
    head: [60, 22],
    torso: [[60, 56], [60, 30]],
    armF: [[60, 36], [66, 44], [70, 50]],
    armB: [[60, 36], [54, 44], [50, 50]],
    legF: [[60, 56], [68, 68], [72, 82]],
    legB: [[60, 56], [54, 70], [50, 84]],
  },
  {
    // 5 — the final stage: standing, phone raised, head bowed to the screen
    head: [62, 22],
    torso: [[60, 56], [60, 30]],
    armF: [[60, 37], [69, 42], [71, 32]],
    armB: [[60, 37], [55, 46], [52, 52]],
    legF: [[60, 56], [63, 70], [64, 84]],
    legB: [[60, 56], [57, 70], [56, 84]],
  },
]
/* STAGES-END */

const HOLD_MS = 420 // pose rests briefly so each stage registers…
const MORPH_MS = 850 // …then flows into the next
const SEG_MS = HOLD_MS + MORPH_MS
const CYCLE_MS = SEG_MS * STAGES.length // last segment morphs 5 → 1 (the loop)

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const smooth = (t: number) => t * t * (3 - 2 * t) // smoothstep easing

function mixPts(a: readonly Pt[], b: readonly Pt[], t: number): string {
  let d = ''
  for (let i = 0; i < a.length; i++) {
    d += `${i === 0 ? 'M' : 'L'}${lerp(a[i][0], b[i][0], t)} ${lerp(a[i][1], b[i][1], t)}`
  }
  return d
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
      armF: el('armF'),
      armB: el('armB'),
      legF: el('legF'),
      legB: el('legB'),
      phone: el('phone'),
    }
    if (Object.values(parts).some((p) => !p)) return

    const finalPose = () => apply(STAGES.length - 1, STAGES.length - 1, 0, 1)

    function apply(i: number, j: number, tRaw: number, phoneAlpha: number) {
      const t = smooth(tRaw)
      const a = STAGES[i]
      const b = STAGES[j]
      parts.head!.setAttribute('cx', String(lerp(a.head[0], b.head[0], t)))
      parts.head!.setAttribute('cy', String(lerp(a.head[1], b.head[1], t)))
      for (const key of ['torso', 'armF', 'armB', 'legF', 'legB'] as const) {
        parts[key]!.setAttribute('d', mixPts(a[key], b[key], t))
      }
      // The phone rides the front hand (last armF point).
      const hx = lerp(a.armF[2][0], b.armF[2][0], t)
      const hy = lerp(a.armF[2][1], b.armF[2][1], t)
      parts.phone!.setAttribute('transform', `translate(${hx} ${hy}) rotate(-14)`)
      parts.phone!.setAttribute('opacity', String(phoneAlpha))
    }

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      finalPose()
      return
    }

    let raf = 0
    const t0 = performance.now()
    const last = STAGES.length - 1

    const tick = (now: number) => {
      const cycle = (now - t0) % CYCLE_MS
      const seg = Math.floor(cycle / SEG_MS) // 0..4; seg k morphs stage k → k+1 (wrapping)
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
        <circle data-part="head" r="6" fill="currentColor" stroke="none" />
        <path data-part="torso" />
        <path data-part="armB" />
        <path data-part="legB" />
        <path data-part="legF" />
        <path data-part="armF" />
        {/* the smartphone, anchored to the front hand */}
        <g data-part="phone" opacity="0">
          <rect x="-2.5" y="-11" width="8" height="14" rx="1.8" fill="currentColor" stroke="none" />
          <rect className="evo-screen" x="-1" y="-9" width="5" height="9" rx="0.9" stroke="none" />
        </g>
      </g>
    </svg>
  )
}
