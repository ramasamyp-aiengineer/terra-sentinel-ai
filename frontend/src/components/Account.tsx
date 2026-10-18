import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check, ChevronDown, KeyRound, LogOut, X } from 'lucide-react'
import { api } from '../api/client'
import { useAuth, useLogout } from '../lib/auth'
import { Btn, ErrorBox, Notice } from './ui'

/** A modal built on the native <dialog>: focus is trapped, Esc closes, and the page behind is inert. */
export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  useEffect(() => {
    const d = ref.current
    if (d && !d.open) d.showModal()
    // No cleanup that calls close(): it fires a 'close' event, which would tell the parent to unmount the dialog it
    // just opened (React StrictMode runs effects twice in development). Removing the element ends the modal state.
  }, [])
  return (
    <dialog ref={ref} className="modal" aria-labelledby={titleId} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()} onKeyDown={(e) => e.key === 'Escape' && (e.preventDefault(), onClose())}>
      <div className="modal-card">
        <header className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}

export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const { passwordMin } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const m = useMutation({ mutationFn: () => api.changePassword(current, next) })

  const tooShort = next.length > 0 && next.length < passwordMin
  const mismatch = again.length > 0 && next !== again
  const ready = current.length > 0 && next.length >= passwordMin && next === again

  return (
    <Modal title="Change password" onClose={onClose}>
      {m.isSuccess ? (
        <div className="stack tight">
          <Notice tone="ok" icon={Check}>
            Password changed. Any other device you were signed in on has been signed out.
          </Notice>
          <div className="btn-row">
            <Btn variant="primary" onClick={onClose}>
              Done
            </Btn>
          </div>
        </div>
      ) : (
        <form
          className="stack tight"
          onSubmit={(e) => {
            e.preventDefault()
            if (ready) m.mutate()
          }}
        >
          <label className="field">
            <span className="field-label">Current password</span>
            <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} autoFocus />
          </label>
          <label className="field">
            <span className="field-label">New password</span>
            <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} aria-invalid={tooShort} />
            <span className={`field-hint ${tooShort ? 'warn-text' : ''}`}>At least {passwordMin} characters. A short sentence works well.</span>
          </label>
          <label className="field">
            <span className="field-label">New password again</span>
            <input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} aria-invalid={mismatch} />
            {mismatch && <span className="field-hint warn-text">The two entries do not match.</span>}
          </label>
          {m.error && <ErrorBox error={m.error} />}
          <div className="btn-row">
            <Btn type="submit" variant="primary" icon={KeyRound} disabled={!ready} loading={m.isPending}>
              Change password
            </Btn>
            <Btn type="button" onClick={onClose}>
              Cancel
            </Btn>
          </div>
        </form>
      )}
    </Modal>
  )
}

const initials = (name: string) =>
  name
    .split(/[\s._@-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join('') || '?'

export function AccountMenu() {
  const { user, authEnabled } = useAuth()
  const logout = useLogout()
  const [open, setOpen] = useState(false)
  const [changing, setChanging] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  if (!user) return null
  return (
    <div className="account" ref={root}>
      <button className="account-btn" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} aria-label={`Account menu for ${user.display_name}`}>
        <span className="avatar" aria-hidden>
          {initials(user.display_name)}
        </span>
        <span className="account-name">{user.display_name}</span>
        <ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="account-menu" role="menu">
          <div className="account-who">
            <strong>{user.display_name}</strong>
            <span className="muted">
              {user.username} · {user.role}
            </span>
          </div>
          {authEnabled && (
            <>
              <button role="menuitem" className="menu-item" onClick={() => { setOpen(false); setChanging(true) }}>
                <KeyRound size={15} aria-hidden /> Change password
              </button>
              <button role="menuitem" className="menu-item" onClick={() => logout.mutate()} disabled={logout.isPending}>
                <LogOut size={15} aria-hidden /> Sign out
              </button>
            </>
          )}
          {!authEnabled && <p className="muted menu-note">Sign-in is switched off on this server (local development).</p>}
        </div>
      )}
      {changing && <ChangePasswordDialog onClose={() => setChanging(false)} />}
    </div>
  )
}
