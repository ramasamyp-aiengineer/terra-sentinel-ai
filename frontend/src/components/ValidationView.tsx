import { CheckCircle2, XCircle } from 'lucide-react'
import type { ParseResultPayload, ValidationReport } from '../api/types'
import { int } from '../lib/format'
import { Chip, Notice } from './ui'

function Preview({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null
  const cols = Object.keys(rows[0]).slice(0, 8)
  return (
    <div className="table-wrap preview">
      <table className="table dense">
        <caption className="sr-only">First rows that will be imported</caption>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} className="mono">
                  {r[c] == null ? '' : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ReportCard({ r }: { r: ValidationReport }) {
  const mapped = Object.entries(r.mapped_columns)
  return (
    <div className={`report ${r.ok ? 'ok' : 'bad'}`}>
      <div className="report-head">
        {r.ok ? <CheckCircle2 size={16} aria-hidden /> : <XCircle size={16} aria-hidden />}
        <strong>{r.kind}</strong>
        <Chip tone={r.ok ? 'ok' : 'bad'}>{r.ok ? 'Ready to import' : 'Needs fixing'}</Chip>
        <span className="muted">
          {int(r.rows_ok)} of {int(r.rows_in)} rows valid
          {r.rows_rejected > 0 && ` · ${int(r.rows_rejected)} rejected`}
        </span>
      </div>

      {r.blocked_reason && <Notice tone="bad">{r.blocked_reason}</Notice>}

      {r.errors.length > 0 && (
        <ul className="issue-list bad" aria-label="Errors">
          {r.errors.slice(0, 8).map((e, i) => (
            <li key={i}>
              <span className="mono">row {e.row}</span> <strong>{e.field}</strong>: {e.message}
            </li>
          ))}
          {r.errors.length > 8 && <li className="muted">and {r.errors.length - 8} more</li>}
        </ul>
      )}
      {r.warnings.length > 0 && (
        <ul className="issue-list warn" aria-label="Warnings">
          {r.warnings.slice(0, 6).map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {mapped.length > 0 && (
        <details className="mapped">
          <summary>How your columns were read ({mapped.length})</summary>
          <div className="chips">
            {mapped.map(([from, to]) => (
              <Chip key={from}>
                {from} → <strong>{to}</strong>
              </Chip>
            ))}
          </div>
        </details>
      )}
      <Preview rows={r.preview} />
    </div>
  )
}

export function ResultView({ result }: { result: ParseResultPayload }) {
  return (
    <div className="stack tight">
      {result.reports.map((r, i) => (
        <ReportCard key={r.kind + i} r={r} />
      ))}
      {result.applied && result.written && (
        <Notice tone="ok" icon={CheckCircle2}>
          <strong>Imported.</strong>{' '}
          {Object.entries(result.written)
            .map(([k, v]) => `${int(v.written)} ${k}`)
            .join(', ')}
          . Alerts, outlooks and trends are being recomputed.
          {result.post_checks?.map((c) => (
            <div key={c.message} className={c.level === 'warning' ? 'warn-text' : 'muted'}>
              {c.message}
            </div>
          ))}
        </Notice>
      )}
    </div>
  )
}
