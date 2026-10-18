import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Database, ExternalLink, Globe2, MapPinned, Satellite } from 'lucide-react'
import { api } from '../api/client'
import { navigate } from '../lib/router'
import { Btn } from './ui'

const ACK_KEY = 'terrasentinel.data-ack.v2'

/**
 * One-time data briefing after sign-in: what is active in this workspace,
 * which corridors are covered, and how to bring more data in as you scale.
 */
export function DataAck() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(ACK_KEY) !== '1'
    } catch {
      return true
    }
  })
  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: api.meta, enabled: open })
  const { data: regions } = useQuery({ queryKey: ['regions'], queryFn: api.regions, enabled: open })
  const { data: status } = useQuery({ queryKey: ['data-status'], queryFn: api.dataStatus, enabled: open })

  if (!open) return null

  const dismiss = () => {
    try {
      localStorage.setItem(ACK_KEY, '1')
    } catch {
      /* private mode */
    }
    setOpen(false)
  }

  const named = (regions ?? []).filter((r) => r.level === 'district' || r.level === 'state').slice(0, 10)
  const points = status?.counts?.points
  const epochs = status?.counts?.epochs
  const siteCount = meta?.sites

  return (
    <div className="ack-backdrop" role="presentation">
      <div className="ack-dialog" role="dialog" aria-modal="true" aria-labelledby="ack-title" aria-describedby="ack-lead">
        <header className="ack-head">
          <div className="ack-icon" aria-hidden>
            <Satellite size={22} />
          </div>
          <div>
            <h2 id="ack-title">Before you start</h2>
            <p id="ack-lead" className="ack-lead">
              A short briefing on the data active in this workspace, and how to connect more when you are ready.
            </p>
          </div>
        </header>

        <div className="ack-grid">
          <section className="ack-card">
            <h3 className="ack-h">
              <Database size={15} aria-hidden /> Active dataset
            </h3>
            <p className="ack-body">
              {meta?.is_demo !== false ? (
                <>
                  This workspace is running the <strong>demonstration InSAR dataset</strong> (clearly labelled in the product).
                  Motion values are synthetic so you can explore the full workflow safely; geography is real corridor context.
                </>
              ) : (
                <>This workspace is serving your connected operational dataset.</>
              )}
            </p>
            <ul className="ack-stats">
              {siteCount != null && (
                <li>
                  <strong>{siteCount}</strong>
                  <span>ranked sites</span>
                </li>
              )}
              {points != null && (
                <li>
                  <strong>{points.toLocaleString()}</strong>
                  <span>scatterers</span>
                </li>
              )}
              {epochs != null && (
                <li>
                  <strong>{epochs}</strong>
                  <span>epochs</span>
                </li>
              )}
            </ul>
            <p className="ack-body">
              File layouts follow common open InSAR exports so your own CSVs and GeoJSON import through Data Hub without a rebuild.
            </p>
            <div className="ack-links">
              <a href="https://egms.land.copernicus.eu/" target="_blank" rel="noreferrer">
                Copernicus EGMS <ExternalLink size={12} aria-hidden />
              </a>
              <a href="https://comet.nerc.ac.uk/comet-lics-portal/" target="_blank" rel="noreferrer">
                COMET-LiCSAR <ExternalLink size={12} aria-hidden />
              </a>
              <button
                type="button"
                className="link-btn"
                onClick={() => {
                  dismiss()
                  navigate('/methodology')
                }}
              >
                How numbers are computed
              </button>
            </div>
          </section>

          <section className="ack-card">
            <h3 className="ack-h">
              <MapPinned size={15} aria-hidden /> Coverage today
            </h3>
            <p className="ack-body">
              Focused Indian infrastructure corridors — highways, metro, and a dam — so the map stays decision-ready rather than nation-wide noise.
            </p>
            <ul className="ack-chips">
              {named.map((r) => (
                <li key={r.region_id}>{r.name}</li>
              ))}
            </ul>
          </section>

          <section className="ack-card ack-card-wide">
            <h3 className="ack-h">
              <Globe2 size={15} aria-hidden /> Grow coverage when you need it
            </h3>
            <p className="ack-body">
              Scale by connecting data live — validate, import, and the rankings update. No redeploy for new files.
            </p>
            <ul className="ack-list">
              <li>
                <strong>Data Hub</strong> — points, time series, rainfall, assets, regions, or a wide InSAR product.
              </li>
              <li>
                <strong>Link fetch</strong> and <strong>Open-Meteo rainfall</strong> for a chosen region.
              </li>
              <li>
                <strong>Earthquake catalogs</strong> as nearby context only; they never change the risk score.
              </li>
              <li>
                <strong>Cloud warehouse</strong> when your organisation stores observations in BigQuery.
              </li>
            </ul>
          </section>
        </div>

        <footer className="ack-foot">
          <p className="ack-note">Early-warning outlooks are time-to-threshold bands if the current trend continues — not failure dates.</p>
          <div className="ack-actions">
            <Btn
              variant="secondary"
              onClick={() => {
                dismiss()
                navigate('/data')
              }}
            >
              Open Data Hub
            </Btn>
            <Btn variant="primary" onClick={dismiss}>
              Continue to Command Center
            </Btn>
          </div>
        </footer>
      </div>
    </div>
  )
}
