/** The "AI supported Reporting" easter egg: the March of Progress, animated.
 *
 *  Five pictogram silhouettes walk in from the left — crawling, knuckle-walking,
 *  hunched, upright — and the final stage of evolution stands reading a glowing
 *  smartphone. Figures appear in sequence and the loop restarts, making it a
 *  playful progress indicator while the report LLM is analysing.
 *
 *  Pure SVG + CSS keyframes (see .evo-* in styles.css); theme-aware via
 *  currentColor. */

const HEAD_R = 6

function Head({ cx, cy }: { cx: number; cy: number }) {
  return <circle cx={cx} cy={cy} r={HEAD_R} fill="currentColor" stroke="none" />
}

export function EvolutionLoader() {
  return (
    <svg
      className="evo"
      viewBox="0 0 340 92"
      role="img"
      aria-label="Evolution from crawling to the smartphone — the report is being generated"
    >
      {/* ground */}
      <line className="evo-ground" x1="8" y1="84" x2="332" y2="84" />

      {/* 1 — crawling on all fours */}
      <g className="evo-fig evo-f1">
        <Head cx={52} cy={64} />
        <path d="M20 70 L44 65" />
        <path d="M40 66 L44 82" />
        <path d="M34 67 L30 82" />
        <path d="M22 70 L16 82" />
        <path d="M24 70 L28 82" />
      </g>

      {/* 2 — knuckle-walking */}
      <g className="evo-fig evo-f2">
        <Head cx={112} cy={49} />
        <path d="M86 72 L106 54" />
        <path d="M102 58 L114 82" />
        <path d="M99 61 L104 82" />
        <path d="M86 72 L80 82" />
        <path d="M87 72 L93 82" />
      </g>

      {/* 3 — hunched, almost upright */}
      <g className="evo-fig evo-f3">
        <Head cx={172} cy={37} />
        <path d="M160 66 L170 43" />
        <path d="M166 50 L172 66" />
        <path d="M165 52 L160 65" />
        <path d="M160 66 L154 82" />
        <path d="M160 66 L166 82" />
      </g>

      {/* 4 — upright, mid-stride */}
      <g className="evo-fig evo-f4">
        <Head cx={230} cy={24} />
        <path d="M230 31 L230 56" />
        <path d="M230 38 L221 52" />
        <path d="M230 38 L239 50" />
        <path d="M230 56 L220 82" />
        <path d="M230 56 L240 80" />
      </g>

      {/* 5 — the final stage: standing, phone in hand, head bowed to the screen */}
      <g className="evo-fig evo-f5">
        <Head cx={292} cy={23} />
        <path d="M290 30 L290 56" />
        <path d="M290 37 L283 52" />
        {/* bent arm raising the phone towards the face */}
        <path d="M290 38 L299 42 L300 33" />
        <path d="M290 56 L284 82" />
        <path d="M290 56 L296 82" />
        {/* the smartphone (slightly tilted towards the face) */}
        <g transform="rotate(-14 301 26)">
          <rect x="297.5" y="19" width="8" height="14" rx="1.8" fill="currentColor" stroke="none" />
          <rect className="evo-screen" x="299" y="21" width="5" height="9" rx="0.9" stroke="none" />
        </g>
      </g>
    </svg>
  )
}
