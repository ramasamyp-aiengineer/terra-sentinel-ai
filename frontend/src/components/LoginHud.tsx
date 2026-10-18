import { TIER_HEX, TIER_LABEL, TIER_ORDER } from '../lib/tier'

export function LoginCallout() {
  return (
    <article className="login-callout">
      <header>
        <span className="login-tier">Critical</span>
        <span className="login-state">Accelerating</span>
      </header>
      <h2>NH-58 Himalayan Corridor · KM 2.50–2.75</h2>
      <p>
        To threshold <strong>103–154 days</strong>
        <span> if today&apos;s trend continues. Not a failure date.</span>
      </p>
      <svg className="login-spark" viewBox="0 0 180 36" aria-hidden>
        <line x1="0" y1="6" x2="180" y2="6" stroke="#C62828" strokeDasharray="3 3" />
        <path d="M 0 32 C 40 30, 70 26, 95 18 L 118 12" fill="none" stroke="#0f766e" strokeWidth="2" />
        <polygon points="118,12 148,6 180,6" fill="#0f766e" fillOpacity="0.18" />
        <circle cx="118" cy="12" r="3" fill="#C62828" />
      </svg>
      <p className="login-illust">Illustration using demonstration sites. Sign in for the live map.</p>
    </article>
  )
}

export function LoginLegend() {
  return (
    <div className="login-legend">
      {TIER_ORDER.map((t) => (
        <span key={t}>
          <i style={{ background: TIER_HEX[t] }} />
          {TIER_LABEL[t]}
        </span>
      ))}
    </div>
  )
}
