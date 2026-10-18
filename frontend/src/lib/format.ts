/** Speed magnitude with unit. Sign is shown separately as direction text. */
export const mmMonth = (v: number) => `${Math.abs(v).toFixed(1)} mm/month`
export const mm = (v: number, digits = 1) => `${Math.abs(v).toFixed(digits)} mm`

export function etaText(low: number | null, high: number | null, status: string): string {
  if (status === 'threshold_exceeded') return 'Threshold exceeded'
  if (status === 'approaching' && low != null && high != null) return `${low}-${high} days`
  if (status === 'no_crossing_expected') return 'No crossing expected'
  return 'No outlook'
}

export const chainage = (a: number, b: number) => `KM ${a.toFixed(2)}-${b.toFixed(2)}`

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return 'n/a'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' })
}

export function dateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export const int = (n: number) => n.toLocaleString('en-US')

export function plural(n: number, one: string, many = `${one}s`) {
  return `${int(n)} ${n === 1 ? one : many}`
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function sourceLabel(src: string): { text: string; tone: 'warn' | 'info' | 'ok'; hint: string } {
  if (src === 'DEMO-SYNTHETIC')
    return { text: 'Demonstration data', tone: 'warn', hint: 'Motion and rainfall values are synthetic and follow the schema of real InSAR products.' }
  if (src === 'mixed')
    return { text: 'Mixed data', tone: 'info', hint: 'Demonstration data and uploaded data are both present. Check dataset provenance in the Data Hub.' }
  return { text: 'Observed data', tone: 'ok', hint: 'All scatterers come from uploaded or fetched observations.' }
}
