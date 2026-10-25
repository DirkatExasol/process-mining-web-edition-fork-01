/** A tiny inline-SVG sparkline for a weekly ingest series. The series ends at the current
 *  week, so a run of trailing zeros is the gap between the last ingest and today — drawn as
 *  a dashed flat baseline to make "nothing recently" read at a glance. Pure presentational,
 *  theme-aware (uses the app's CSS tokens), no dependencies. */

interface SparklineProps {
  values: number[]
  width?: number
  height?: number
  /** Accessible/title text, e.g. "Ingests over the last 12 weeks". */
  label?: string
}

export function Sparkline({ values, width = 168, height = 40, label }: SparklineProps) {
  const n = values.length
  const pad = 3
  const w = width
  const h = height
  const max = Math.max(1, ...values)
  const stepX = n > 1 ? (w - pad * 2) / (n - 1) : 0
  const x = (i: number) => pad + i * stepX
  const y = (v: number) => h - pad - (v / max) * (h - pad * 2)

  if (n === 0) {
    return <svg className="spark" width={w} height={h} aria-label={label} role="img" />
  }

  // Index of the last week that actually had ingests; everything after it is the gap-to-now.
  let lastNonZero = -1
  for (let i = n - 1; i >= 0; i--) {
    if (values[i] > 0) {
      lastNonZero = i
      break
    }
  }

  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
  // The solid line runs through the active part; the flat dashed tail spans the recency gap.
  const activeEnd = lastNonZero < 0 ? 0 : lastNonZero
  const solid = pts.slice(0, activeEnd + 1).join(' ')
  const baseY = (h - pad).toFixed(1)
  const areaPath =
    lastNonZero < 0
      ? ''
      : `M ${x(0).toFixed(1)},${baseY} L ${pts.slice(0, activeEnd + 1).join(' L ')} L ${x(activeEnd).toFixed(1)},${baseY} Z`

  return (
    <svg
      className="spark"
      // Fill the container width; `width`/`height` only define the coordinate space so the
      // chart stays crisp while stretching to whatever card it sits in.
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      {label && <title>{label}</title>}
      {/* baseline */}
      <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} className="spark-base" />
      {areaPath && <path d={areaPath} className="spark-area" />}
      {lastNonZero >= 0 && <polyline points={solid} className="spark-line" fill="none" />}
      {/* the gap-to-now: a flat dashed segment from the last ingest to today */}
      {lastNonZero >= 0 && lastNonZero < n - 1 && (
        <line
          x1={x(lastNonZero).toFixed(1)}
          y1={baseY}
          x2={x(n - 1).toFixed(1)}
          y2={baseY}
          className="spark-gap"
        />
      )}
      {/* marker on the most recent ingest */}
      {lastNonZero >= 0 && (
        <circle cx={x(lastNonZero).toFixed(1)} cy={y(values[lastNonZero]).toFixed(1)} r={2.4} className="spark-dot" />
      )}
      {lastNonZero < 0 && (
        <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} className="spark-gap" />
      )}
    </svg>
  )
}
