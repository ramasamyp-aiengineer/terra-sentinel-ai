import { useQuery } from '@tanstack/react-query'
import { Printer, ScrollText } from 'lucide-react'
import { api } from '../api/client'
import { ActList } from '../components/ActList'
import { Btn, Card, Chip, ErrorBox, Loading, PageHeader, TierBar } from '../components/ui'
import { shortDate } from '../lib/format'
import { navigate } from '../lib/router'
import { useUi } from '../store'

export default function BriefPage() {
  const regionId = useUi((s) => s.regionId)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['brief', regionId], queryFn: () => api.brief(regionId) })

  return (
    <div className="page page-narrow">
      <PageHeader
        title="Morning Brief"
        subtitle={data ? `${data.region_name} · as of ${shortDate(data.as_of)}` : undefined}
        actions={
          <>
            <Btn icon={ScrollText} onClick={() => navigate('/workorders')}>
              Work orders
            </Btn>
            <Btn variant="primary" icon={Printer} onClick={() => window.print()}>
              Print / save PDF
            </Btn>
          </>
        }
      />
      {isLoading && <Loading label="Preparing brief" />}
      {error && <ErrorBox error={error} onRetry={() => refetch()} />}
      {data && (
        <article className="brief print-area">
          <div className="brief-hero">
            <h2>{data.headline}</h2>
            <TierBar counts={data.counts} legend height={12} />
            <div className="brief-prov">
              <Chip tone="neutral" title={data.note}>
                Written from computed values, no model guesses
              </Chip>
            </div>
          </div>

          {data.sections.map((s) => (
            <Card key={s.title} title={s.title} className="brief-section">
              <ul className="brief-list">
                {s.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </Card>
          ))}

          {data.top_actions.length > 0 && (
            <Card title="Top actions" subtitle="Open a site for evidence, outlook and a drafted work order." className="no-print">
              <ActList sites={data.top_actions} />
            </Card>
          )}
          <p className="muted foot-note">Decision support for qualified engineers. Outlooks assume the current motion regime continues and are not predictions of failure.</p>
        </article>
      )}
    </div>
  )
}
