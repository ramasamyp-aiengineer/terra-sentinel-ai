import { useMemo } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TimeSeries } from '../api/types'

export type ChartMode = 'trend' | 'history' | 'outlook'

const DAY = 86_400_000
const C = {
  motion: '#0F766E',
  band: '#0F766E',
  rain: '#3B82A0',
  constant: '#5E6C7E',
  accel: '#B85209',
  threshold: '#C62828',
  grid: '#E7EBF0',
  axis: '#5E6C7E',
}

interface Row {
  t: number
  disp?: number
  band?: [number, number]
  rain?: number
  constant?: number
  accel?: number
}

const fmtTick = (t: number) =>
  new Date(t).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' })

export function MotionChart({ ts, mode, height = 260 }: { ts: TimeSeries; mode: ChartMode; height?: number }) {
  const { rows, domain, showThreshold } = useMemo(() => {
    const lastT = Date.parse(ts.last_epoch)
    const windowDays = mode === 'trend' ? 120 : mode === 'outlook' ? 200 : Infinity
    const minT = Number.isFinite(windowDays) ? lastT - windowDays * DAY : -Infinity

    const out: Row[] = []
    ts.dates.forEach((d, i) => {
      const t = Date.parse(d)
      if (t < minT) return
      const q25 = ts.q25_mm[i]
      const q75 = ts.q75_mm[i]
      out.push({
        t,
        disp: ts.disp_mm[i],
        band: mode === 'outlook' || q25 == null || q75 == null ? undefined : [q25, q75],
      })
    })

    if (mode !== 'outlook') {
      ts.rain.forEach((r) => {
        const t = Date.parse(r.date)
        if (t >= minT && t <= lastT + 7 * DAY) out.push({ t, rain: r.precip_mm })
      })
    }

    let showThr = false
    if (mode === 'outlook' && ts.projection) {
      const p = ts.projection
      p.days_ahead.forEach((k, i) => {
        out.push({
          t: lastT + k * DAY,
          constant: p.constant_mm[i],
          accel: p.accelerating_mm ? p.accelerating_mm[i] : undefined,
        })
      })
      showThr = true
    }
    out.sort((a, b) => a.t - b.t)
    const maxT = out.length ? out[out.length - 1].t : lastT
    const minRow = out.length ? out[0].t : lastT
    return { rows: out, domain: [minRow, maxT] as [number, number], showThreshold: showThr }
  }, [ts, mode])

  const hasRain = mode !== 'outlook' && ts.rain.length > 0
  const lastT = Date.parse(ts.last_epoch)

  return (
    <div style={{ width: '100%', height }} role="img" aria-label={`${mode} displacement chart`}>
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 8, right: hasRain ? 4 : 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke={C.grid} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={domain}
            tickFormatter={fmtTick}
            tick={{ fill: C.axis, fontSize: 11 }}
            stroke={C.grid}
            tickCount={6}
          />
          <YAxis
            yAxisId="mm"
            tick={{ fill: C.axis, fontSize: 11 }}
            stroke={C.grid}
            width={44}
            tickFormatter={(v) => `${v}`}
            label={{ value: 'mm (LOS)', angle: -90, position: 'insideLeft', fill: C.axis, fontSize: 10, dx: 14 }}
            domain={['auto', 'auto']}
          />
          {hasRain && (
            <YAxis
              yAxisId="rain"
              orientation="right"
              tick={{ fill: C.axis, fontSize: 11 }}
              stroke={C.grid}
              width={34}
              domain={[0, (max: number) => Math.max(40, max * 3)]}
            />
          )}
          <Tooltip
            contentStyle={{ background: '#FFFFFF', border: '1px solid #D5DBE3', borderRadius: 6, fontSize: 12 }}
            labelStyle={{ color: '#46566A' }}
            labelFormatter={(t) => new Date(Number(t)).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
            formatter={(v, name) => [Array.isArray(v) ? `${v[0]} to ${v[1]} mm` : `${v}`, String(name)]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: '#46566A' }} iconSize={10} />

          {mode !== 'outlook' && (
            <Area
              yAxisId="mm"
              dataKey="band"
              name="Scatterer spread (25-75%)"
              stroke="none"
              fill={C.band}
              fillOpacity={0.16}
              connectNulls
              isAnimationActive={false}
            />
          )}
          {hasRain && (
            <Bar yAxisId="rain" dataKey="rain" name="Rain (mm/day)" fill={C.rain} fillOpacity={0.55} barSize={3} isAnimationActive={false} />
          )}
          <Line
            yAxisId="mm"
            dataKey="disp"
            name="Displacement"
            stroke={C.motion}
            strokeWidth={2}
            dot={mode === 'history' ? false : { r: 2.5, fill: C.motion }}
            connectNulls
            isAnimationActive={false}
          />
          {mode === 'outlook' && (
            <>
              <Line yAxisId="mm" dataKey="constant" name="Constant speed" stroke={C.constant} strokeWidth={1.75} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
              <Line yAxisId="mm" dataKey="accel" name="Accelerating" stroke={C.accel} strokeWidth={1.75} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
              <ReferenceLine yAxisId="mm" x={lastT} stroke="#5E6C7E" strokeDasharray="2 3" label={{ value: 'Last pass', fill: '#5E6C7E', fontSize: 10, position: 'insideTopLeft' }} />
            </>
          )}
          {showThreshold && ts.projection && (
            <ReferenceLine
              yAxisId="mm"
              y={ts.projection.threshold_level_mm}
              stroke={C.threshold}
              strokeDasharray="6 4"
              label={{ value: `Operational threshold (${ts.threshold_mm} mm)`, fill: C.threshold, fontSize: 10, position: 'insideBottomRight' }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
