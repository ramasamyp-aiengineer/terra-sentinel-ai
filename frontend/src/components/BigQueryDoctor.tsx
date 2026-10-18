import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, CircleDashed, ShieldCheck, TriangleAlert, XCircle } from 'lucide-react'
import { api } from '../api/client'
import type { DoctorCheck, DoctorResult } from '../api/types'
import { Btn, ErrorBox, Notice } from './ui'

const MARK: Record<DoctorCheck['status'], { icon: typeof CheckCircle2; cls: string; word: string }> = {
  pass: { icon: CheckCircle2, cls: 'doc-pass', word: 'OK' },
  warn: { icon: TriangleAlert, cls: 'doc-warn', word: 'Note' },
  fail: { icon: XCircle, cls: 'doc-fail', word: 'Fix' },
  skip: { icon: CircleDashed, cls: 'doc-skip', word: 'Skipped' },
}
const TONE: Record<DoctorResult['state'], 'ok' | 'info' | 'warn' | 'bad'> = { ready: 'ok', 'ready-with-notes': 'warn', 'ready-not-active': 'info', blocked: 'bad' }

/** Runs the read-only connection checks and shows the exact fix for anything that fails. */
export function BigQueryDoctor() {
  const m = useMutation({ mutationFn: api.bigQueryDoctor })
  return (
    <div className="stack tight">
      <div className="btn-row">
        <Btn icon={ShieldCheck} loading={m.isPending} onClick={() => m.mutate()}>
          {m.data ? 'Run checks again' : 'Run connection checks'}
        </Btn>
      </div>
      <p className="muted">Read-only: it never writes data or creates anything. Without Google Cloud credentials this can take up to half a minute.</p>
      {m.error && <ErrorBox error={m.error} />}
      {m.data && (
        <>
          <Notice tone={TONE[m.data.state]}>{m.data.headline}</Notice>
          <ol className="doctor">
            {m.data.checks.map((c) => {
              const { icon: Icon, cls, word } = MARK[c.status]
              return (
                <li key={c.id} className={cls}>
                  <Icon size={16} aria-hidden />
                  <div>
                    <strong>
                      {c.label} <span className="doc-word">{word}</span>
                    </strong>
                    <p>{c.detail}</p>
                    {c.fix && (c.status === 'fail' || c.status === 'warn') && <p className="doc-fix">{c.fix}</p>}
                  </div>
                </li>
              )
            })}
          </ol>
        </>
      )}
    </div>
  )
}
