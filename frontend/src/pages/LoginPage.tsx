import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { AlertCircle, Eye, EyeOff, FileCheck2, Gauge, Lock, SatelliteDish } from 'lucide-react'
import { ApiError } from '../api/client'
import { BrandWordmark } from '../components/brand/BrandLogo'
import { LoginCallout, LoginLegend } from '../components/LoginHud'
import { Btn } from '../components/ui'
import { useLogin } from '../lib/auth'

const LoginMap = lazy(() => import('../components/LoginMap'))

const POINTS = [
  { icon: SatelliteDish, title: 'Ranked by consequence', text: 'Satellite ground-motion measurements, ordered by what each site could affect.' },
  { icon: Gauge, title: 'Honest outlooks', text: 'Time-to-threshold bands that assume today\u2019s trend continues. Never a failure date.' },
  { icon: FileCheck2, title: 'Traceable', text: 'Every number links back to its source data and the method that produced it.' },
]

function explain(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'That username and password do not match. Check both and try again.'
    if (error.status === 429) return error.message
    if (error.status === 0) return 'Cannot reach the server. Check your connection, or that the backend is running.'
    if (error.status === 403) return 'This request was blocked. Reload the page and try again.'
  }
  return 'Sign-in failed because of a problem on our side. Try again in a moment.'
}

export function LoginPage({ expired, unreachable, onRetry }: { expired?: boolean; unreachable?: boolean; onRetry?: () => void }) {
  const login = useLogin()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [caps, setCaps] = useState(false)
  const [missing, setMissing] = useState(false)
  const userRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    userRef.current?.focus()
    document.title = 'Sign in \u00B7 TerraSentinel'
  }, [])

  const ready = username.trim().length > 0 && password.length > 0
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (login.isPending) return
    if (!ready) {
      setMissing(true)
      return
    }
    setMissing(false)
    login.mutate({ username: username.trim(), password })
  }
  const failed = missing && !ready ? 'Enter your username and password.' : login.isError ? explain(login.error) : null

  return (
    <div className="login">
      <aside className="login-brand" aria-label="About TerraSentinel">
        <Suspense fallback={<div className="login-map login-map-wait" />}>
          <LoginMap />
        </Suspense>
        <div className="login-hud">
          <BrandWordmark pulse inverted tagline="Ground-motion early warning" className="login-logo" />
          <h1>Rank moving ground by consequence — act before the next inspection.</h1>
          <ul className="login-points">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} title={text}>
                <Icon size={15} aria-hidden />
                <span>{title}</span>
              </li>
            ))}
          </ul>
        </div>
        <LoginCallout />
        <LoginLegend />
        <p className="login-foot">Decision support for qualified engineers. Not a certified safety system. Imagery © Esri.</p>
      </aside>

      <main className="login-main">
        <form className="login-card" onSubmit={submit} noValidate aria-labelledby="login-title">
          <h2 id="login-title">Sign in</h2>
          <p className="muted">Use the account your administrator created for you.</p>

          {expired && !failed && (
            <div className="notice notice-info" role="status">
              <AlertCircle size={15} aria-hidden />
              <div>Your session ended. Sign in again to continue where you left off.</div>
            </div>
          )}
          {unreachable && (
            <div className="notice notice-warn" role="alert">
              <AlertCircle size={15} aria-hidden />
              <div>
                We could not reach the server.{' '}
                {onRetry && (
                  <button type="button" className="link-btn" onClick={onRetry}>
                    Try again
                  </button>
                )}
              </div>
            </div>
          )}
          {failed && (
            <div className="notice notice-bad" role="alert" id="login-error">
              <AlertCircle size={15} aria-hidden />
              <div>{failed}</div>
            </div>
          )}

          <label className="field">
            <span className="field-label">Username</span>
            <input
              ref={userRef}
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={!!failed}
              aria-describedby={failed ? 'login-error' : undefined}
              maxLength={80}
            />
          </label>

          <label className="field">
            <span className="field-label">Password</span>
            <span className="password-wrap">
              <input
                name="password"
                type={show ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyUp={(e) => setCaps(e.getModifierState('CapsLock'))}
                onKeyDown={(e) => setCaps(e.getModifierState('CapsLock'))}
                aria-invalid={!!failed}
                aria-describedby={failed ? 'login-error' : undefined}
                maxLength={256}
              />
              <button type="button" className="icon-btn show-btn" onClick={() => setShow((v) => !v)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}>
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </span>
            {caps && <span className="field-hint warn-text">Caps Lock is on.</span>}
          </label>

          <Btn type="submit" variant="primary" icon={Lock} loading={login.isPending} className="login-submit">
            Sign in
          </Btn>

          <p className="muted login-help">Forgot your password? Ask an administrator to reset it.</p>
        </form>
        <p className="login-legal muted">Signing in is recorded for security. Sessions end automatically after a while, or when you sign out.</p>
      </main>
    </div>
  )
}
