import { useId, type CSSProperties } from 'react'

/**
 * Animated brand mark for the Process Mining Demonstrator.
 *
 * A small discovered process graph — three nodes joined by directed edges — with
 * an "event" dot continuously flowing around the path, a pulsing discovery node,
 * and a soft shine sweep across the gradient badge. Fills its container, so the
 * surrounding `.brand-logo` / `.logo` box controls the size.
 */
export function Logo({ style, className }: { style?: CSSProperties; className?: string }) {
  const uid = useId().replace(/[:]/g, '')
  const bg = `pmBg-${uid}`
  const shine = `pmShine-${uid}`
  const clip = `pmClip-${uid}`
  const glow = `pmGlow-${uid}`
  return (
    <svg
      className={['pm-logo', className].filter(Boolean).join(' ')}
      style={{ width: '100%', height: '100%', display: 'block', ...style }}
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={bg} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3a9bff" />
          <stop offset="1" stopColor="#6b5cf0" />
        </linearGradient>
        <linearGradient id={shine} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0.5" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <clipPath id={clip}>
          <rect x="2" y="2" width="44" height="44" rx="12" />
        </clipPath>
        <filter id={glow} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="1.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g clipPath={`url(#${clip})`}>
        <rect x="2" y="2" width="44" height="44" rx="12" fill={`url(#${bg})`} />
        <rect x="-28" y="2" width="20" height="44" fill={`url(#${shine})`} transform="skewX(-16)">
          <animate attributeName="x" values="-28;56" dur="4.2s" begin="0.5s" repeatCount="indefinite" />
        </rect>
        <path
          d="M15 16 L33 16 L24 34 Z"
          fill="none"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity="0.85"
        />
        <circle cx="15" cy="16" r="4.4" fill="none" stroke="#fff" strokeWidth="1.5">
          <animate attributeName="r" values="4.4;9" dur="2.8s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.55;0" dur="2.8s" repeatCount="indefinite" />
        </circle>
        <g fill="#fff">
          <circle cx="15" cy="16" r="4.4" />
          <circle cx="33" cy="16" r="4.4" />
          <circle cx="24" cy="34" r="4.4" />
        </g>
        <circle r="2.2" fill="#eaf3ff" filter={`url(#${glow})`}>
          <animateMotion dur="2.8s" repeatCount="indefinite" calcMode="linear" path="M15 16 L33 16 L24 34 Z" />
        </circle>
      </g>
    </svg>
  )
}
