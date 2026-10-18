import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { Card, DataTable, ErrorBox, Loading, Notice, PageHeader, TierBadge } from '../components/ui'

export default function MethodologyPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['methodology'], queryFn: api.methodology, staleTime: Infinity })

  return (
    <div className="page page-narrow">
      <PageHeader title="Methodology" subtitle="Exactly how every number on screen is produced, and where the analysis stops being reliable." />
      {isLoading && <Loading />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}
      {data && (
        <div className="stack">
          <Notice tone="brand">{data.principle}</Notice>

          <Card title="Pipeline">
            <ol className="steps">
              {data.pipeline.map((p, i) => (
                <li key={p.step}>
                  <span className="step-n mono">{i + 1}</span>
                  <div>
                    <strong>{p.step}</strong>
                    <p>{p.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card title="Risk tiers">
            <ul className="plain-list tier-rules">
              {data.tiers.map((t) => (
                <li key={t.tier}>
                  <TierBadge tier={t.tier} /> <span>{t.rule}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Risk Priority Index">
            <p className="formula mono">{data.rpi.formula}</p>
            <dl className="kv stacked">
              <div><dt>Hazard</dt><dd>{data.rpi.hazard}</dd></div>
              <div><dt>Consequence</dt><dd>{data.rpi.consequence}</dd></div>
              <div><dt>Confidence</dt><dd>{data.rpi.confidence}</dd></div>
            </dl>
            <ul className="plain-list">
              {data.rpi.guards.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          </Card>

          <Card title="Asset profiles" subtitle="Thresholds are configurable per asset type." flush>
            <DataTable caption="Per-asset-type thresholds">
              <thead>
                <tr>
                  <th>Asset type</th>
                  <th className="num">Buffer</th>
                  <th className="num">Threshold</th>
                  <th className="num">Window</th>
                  <th className="num">Creep</th>
                  <th className="num">Accel ×</th>
                  <th className="num">Approach</th>
                  <th className="num">Min coh.</th>
                </tr>
              </thead>
              <tbody>
                {data.profiles.map((p) => (
                  <tr key={p.asset_type} title={p.mechanism_hint}>
                    <td>{p.label}</td>
                    <td className="num mono">{p.buffer_m} m</td>
                    <td className="num mono">{p.threshold_mm} mm</td>
                    <td className="num mono">{p.window_days} d</td>
                    <td className="num mono">{p.creep_mm_month} mm/mo</td>
                    <td className="num mono">{p.accel_ratio}</td>
                    <td className="num mono">{p.approach_days} d</td>
                    <td className="num mono">{p.min_coherence}</td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          </Card>

          <Card title="How alerts are raised">
            <ul className="plain-list">
              {data.alerts.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </Card>

          <Card title="Limitations" subtitle="Read these before acting on any output.">
            <ul className="plain-list limits">
              {data.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  )
}
