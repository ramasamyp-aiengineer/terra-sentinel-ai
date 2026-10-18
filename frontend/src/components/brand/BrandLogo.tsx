/**
 * TerraSentinel AI brand mark.
 * Circle badge + pulse waveform (ground motion) + orbital arc (satellite watch).
 * Use `pulse` on the login page so the signal blinks; keep it still in the app chrome.
 */

type Size = 'sm' | 'md' | 'lg'

const SIZES: Record<Size, number> = { sm: 28, md: 36, lg: 48 }

export function BrandMark({ size = 'md', pulse = false, className = '' }: { size?: Size; pulse?: boolean; className?: string }) {
  const px = SIZES[size]
  return (
    <span className={`brand-logo-mark ${pulse ? 'brand-logo-mark--pulse' : ''} ${className}`} style={{ width: px, height: px }} aria-hidden>
      <svg viewBox="0 0 48 48" width={px} height={px} role="img" focusable="false">
        <defs>
          <linearGradient id="ts-badge" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#0f766e" />
            <stop offset="100%" stopColor="#0b5f58" />
          </linearGradient>
        </defs>
        <circle cx="24" cy="24" r="22" fill="url(#ts-badge)" />
        {/* orbital arc: satellite watch */}
        <path d="M10 18 C18 10, 30 10, 38 18" fill="none" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" opacity="0.55" />
        <circle className="brand-sat" cx="34.5" cy="14.5" r="2.2" fill="#fff" />
        {/* ground baseline */}
        <path d="M11 34 H37" stroke="#fff" strokeWidth="1.2" strokeLinecap="round" opacity="0.35" />
        {/* pulse / ground-motion signal */}
        <path
          className="brand-pulse-line"
          d="M11 28 L16 28 L18.5 20 L22 34 L25.5 16 L29 28 L37 28"
          fill="none"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {pulse && (
          <>
            <circle className="brand-pulse-ring" cx="25.5" cy="16" r="3.5" fill="none" stroke="#5eead4" strokeWidth="1.4" />
            <circle className="brand-pulse-dot" cx="25.5" cy="16" r="2.2" fill="#5eead4" />
          </>
        )}
      </svg>
    </span>
  )
}

export function BrandWordmark({
  pulse = false,
  inverted = false,
  tagline,
  className = '',
}: {
  pulse?: boolean
  /** White text for dark/map backgrounds */
  inverted?: boolean
  tagline?: string
  className?: string
}) {
  return (
    <div className={`brand-wordmark ${inverted ? 'brand-wordmark--inverted' : ''} ${className}`}>
      <BrandMark size="md" pulse={pulse} />
      <div className="brand-wordmark-text">
        <div className="brand-wordmark-title">
          TerraSentinel <span className="brand-ai">AI</span>
        </div>
        {tagline && <div className="brand-wordmark-tag">{tagline}</div>}
      </div>
    </div>
  )
}
