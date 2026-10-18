import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, Check, KeyRound, ShieldCheck, UserPlus, Wand2 } from 'lucide-react'
import { api } from '../api/client'
import type { Role, UserRow } from '../api/types'
import { Modal } from '../components/Account'
import { Btn, Card, Chip, DataTable, Empty, ErrorBox, Field, Loading, Notice, PageHeader } from '../components/ui'
import { useAuth } from '../lib/auth'
import { dateTime } from '../lib/format'

const ROLE_INFO: Record<Role, { label: string; can: string }> = {
  viewer: { label: 'Viewer', can: 'Read everything: map, alerts, outlooks, work orders and data sources.' },
  analyst: { label: 'Analyst', can: 'Everything a viewer can, plus act on alerts, draft work orders and export data.' },
  admin: { label: 'Admin', can: 'Everything an analyst can, plus import and fetch data, manage regions and public datasets, and manage people.' },
}

const EVENT_LABEL: Record<string, string> = {
  login: 'Signed in',
  login_failed: 'Failed sign-in',
  login_locked: 'Sign-in blocked (too many attempts)',
  logout: 'Signed out',
  user_created: 'Person added',
  user_updated: 'Person changed',
  password_changed: 'Password changed',
  password_change_failed: 'Password change refused',
  bootstrap_admin: 'First administrator created',
}

/** A readable one-off password for a new account; the person is expected to change it. */
function suggestPassword(): string {
  const words = ['river', 'cedar', 'harbor', 'summit', 'meadow', 'granite', 'lantern', 'orchard', 'falcon', 'willow', 'copper', 'ember']
  const pick = (n: number) => crypto.getRandomValues(new Uint32Array(1))[0]! % n
  return `${words[pick(words.length)]}-${words[pick(words.length)]}-${100 + pick(900)}-${words[pick(words.length)]}`
}

function ResetDialog({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const qc = useQueryClient()
  const [pw, setPw] = useState(suggestPassword())
  const m = useMutation({ mutationFn: () => api.updateUser(user.username, { password: pw }), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) })
  return (
    <Modal title={`Reset password for ${user.display_name}`} onClose={onClose}>
      {m.isSuccess ? (
        <div className="stack tight">
          <Notice tone="ok" icon={Check}>
            Password reset and every session for {user.username} was ended. Give them this password through a private channel and ask them to change it after signing in.
          </Notice>
          <code className="secret">{pw}</code>
          <div className="btn-row">
            <Btn variant="primary" onClick={onClose}>Done</Btn>
          </div>
        </div>
      ) : (
        <form className="stack tight" onSubmit={(e) => { e.preventDefault(); m.mutate() }}>
          <Field label="New temporary password" hint="You will see it once. Minimum 10 characters.">
            <input value={pw} onChange={(e) => setPw(e.target.value)} spellCheck={false} autoComplete="off" />
          </Field>
          {m.error && <ErrorBox error={m.error} />}
          <div className="btn-row">
            <Btn type="submit" variant="primary" icon={KeyRound} loading={m.isPending} disabled={pw.length < 10}>Reset password</Btn>
            <Btn type="button" onClick={() => setPw(suggestPassword())} icon={Wand2}>Suggest another</Btn>
          </div>
        </form>
      )}
    </Modal>
  )
}

function People() {
  const qc = useQueryClient()
  const { user: me } = useAuth()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['users'], queryFn: api.users })
  const [resetting, setResetting] = useState<UserRow | null>(null)
  const patch = useMutation({
    mutationFn: ({ username, ...b }: { username: string; role?: Role; disabled?: boolean }) => api.updateUser(username, b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })

  if (isLoading) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={() => refetch()} />
  const users = data?.users ?? []
  return (
    <Card title="People" subtitle={`${users.length} account${users.length === 1 ? '' : 's'}. Changing a role or disabling someone signs them out immediately.`} flush>
      {patch.error && <div className="card-pad"><ErrorBox error={patch.error} /></div>}
      <DataTable caption="People with access">
        <thead>
          <tr><th>Person</th><th>Role</th><th>Status</th><th>Last sign-in</th><th className="num">Actions</th></tr>
        </thead>
        <tbody>
          {users.map((u) => {
            const self = u.username === me?.username
            return (
              <tr key={u.username}>
                <td>
                  <strong>{u.display_name}</strong> {self && <Chip tone="brand">you</Chip>}
                  <div className="muted mono">{u.username}</div>
                </td>
                <td>
                  <select
                    value={u.role}
                    aria-label={`Role for ${u.username}`}
                    disabled={patch.isPending}
                    onChange={(e) => patch.mutate({ username: u.username, role: e.target.value as Role })}
                  >
                    {(data?.roles ?? []).map((r) => <option key={r} value={r}>{ROLE_INFO[r].label}</option>)}
                  </select>
                </td>
                <td><Chip tone={u.disabled ? 'bad' : 'ok'}>{u.disabled ? 'Disabled' : 'Active'}</Chip></td>
                <td className="mono muted">{u.last_login ? dateTime(u.last_login) : 'never'}</td>
                <td className="num">
                  <div className="btn-row end">
                    <Btn small icon={KeyRound} onClick={() => setResetting(u)}>Reset password</Btn>
                    <Btn small icon={u.disabled ? Check : Ban} disabled={self || patch.isPending} title={self ? 'You cannot disable your own account' : undefined} onClick={() => patch.mutate({ username: u.username, disabled: !u.disabled })}>
                      {u.disabled ? 'Enable' : 'Disable'}
                    </Btn>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </DataTable>
      {resetting && <ResetDialog user={resetting} onClose={() => setResetting(null)} />}
    </Card>
  )
}

function AddPerson() {
  const qc = useQueryClient()
  const [f, setF] = useState({ username: '', display_name: '', role: 'analyst' as Role, password: suggestPassword() })
  const [made, setMade] = useState<{ username: string; password: string } | null>(null)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value })
  const valid = /^[a-z0-9][a-z0-9._@-]{2,39}$/i.test(f.username.trim()) && f.password.length >= 10
  const m = useMutation({
    mutationFn: () => api.createUser({ ...f, username: f.username.trim(), display_name: f.display_name.trim() }),
    onSuccess: () => {
      setMade({ username: f.username.trim().toLowerCase(), password: f.password })
      setF({ username: '', display_name: '', role: 'analyst', password: suggestPassword() })
      qc.invalidateQueries({ queryKey: ['users'] })
    },
  })
  return (
    <Card title="Add a person" subtitle="They sign in with the temporary password you set here, then change it.">
      <form className="stack tight" onSubmit={(e) => { e.preventDefault(); if (valid) m.mutate() }}>
        <div className="form-grid">
          <Field label="Username" hint="Letters, numbers, dot, dash. 3 to 40 characters.">
            <input value={f.username} onChange={set('username')} autoComplete="off" spellCheck={false} autoCapitalize="none" maxLength={40} />
          </Field>
          <Field label="Display name">
            <input value={f.display_name} onChange={set('display_name')} autoComplete="off" maxLength={60} />
          </Field>
          <Field label="Role">
            <select value={f.role} onChange={set('role')}>
              {(['viewer', 'analyst', 'admin'] as Role[]).map((r) => <option key={r} value={r}>{ROLE_INFO[r].label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Temporary password" hint="Shown once after you add them. Minimum 10 characters.">
          <input value={f.password} onChange={set('password')} autoComplete="off" spellCheck={false} />
        </Field>
        <div className="btn-row">
          <Btn type="submit" variant="primary" icon={UserPlus} disabled={!valid} loading={m.isPending}>Add person</Btn>
          <Btn type="button" icon={Wand2} onClick={() => setF({ ...f, password: suggestPassword() })}>Suggest password</Btn>
        </div>
        {m.error && <ErrorBox error={m.error} />}
        {made && (
          <Notice tone="ok" icon={Check}>
            Added <strong>{made.username}</strong>. Share this temporary password privately; it is not shown again:
            <code className="secret">{made.password}</code>
          </Notice>
        )}
      </form>
    </Card>
  )
}

function Roles() {
  return (
    <Card title="What each role can do">
      <dl className="kv roles">
        {(Object.keys(ROLE_INFO) as Role[]).map((r) => (
          <div key={r}>
            <dt><Chip tone={r === 'admin' ? 'brand' : r === 'analyst' ? 'info' : 'neutral'}>{ROLE_INFO[r].label}</Chip></dt>
            <dd>{ROLE_INFO[r].can}</dd>
          </div>
        ))}
      </dl>
    </Card>
  )
}

function Activity() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['audit'], queryFn: () => api.audit(60), staleTime: 15_000 })
  return (
    <Card title="Recent security activity" subtitle="Sign-ins, failures and changes to access. Passwords are never recorded." flush>
      {isLoading && <Loading />}
      {error && <div className="card-pad"><ErrorBox error={error} onRetry={() => refetch()} /></div>}
      {data && data.events.length === 0 && <Empty title="Nothing recorded yet" />}
      {data && data.events.length > 0 && (
        <DataTable caption="Security activity">
          <thead><tr><th>When</th><th>What</th><th>Who</th><th>Detail</th><th>From</th></tr></thead>
          <tbody>
            {data.events.map((e, i) => (
              <tr key={`${e.at}-${i}`}>
                <td className="mono muted">{dateTime(e.at)}</td>
                <td><Chip tone={e.event.includes('failed') || e.event.includes('locked') ? 'warn' : 'neutral'}>{EVENT_LABEL[e.event] ?? e.event}</Chip></td>
                <td className="mono">{e.actor}</td>
                <td className="muted">{e.detail}</td>
                <td className="mono muted">{e.ip || '-'}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </Card>
  )
}

export default function AccessPage() {
  return (
    <div className="page">
      <PageHeader title="Users & access" subtitle="Decide who can see, act on and change what. Every sign-in and change is recorded." actions={<Chip tone="brand" icon={ShieldCheck}>Admin only</Chip>} />
      <People />
      <div className="grid-2 top">
        <AddPerson />
        <Roles />
      </div>
      <Activity />
    </div>
  )
}
