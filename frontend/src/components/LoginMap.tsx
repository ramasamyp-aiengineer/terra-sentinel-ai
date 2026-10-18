import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { TIER_HEX } from '../lib/tier'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

/** Same Esri satellite tiles as the Command Center. Confirm terms of use before a commercial deployment. */
const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    sat: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [{ id: 'sat', type: 'raster', source: 'sat' }],
}

/** NH-58 Himalayan corridor from the demonstration dataset. Shown here as illustration, not a live session. */
const ROAD: [number, number][] = [
  [79.535, 30.535],
  [79.56, 30.545],
  [79.575, 30.565],
  [79.6, 30.575],
]

const SITES: { lon: number; lat: number; tier: keyof typeof TIER_HEX; name: string }[] = [
  { lon: 79.56, lat: 30.545, tier: 'CRITICAL', name: 'KM 2.50–2.75' },
  { lon: 79.548, lat: 30.54, tier: 'ELEVATED', name: 'KM 1.25–1.50' },
  { lon: 79.575, lat: 30.565, tier: 'WATCH', name: 'KM 4.00–4.25' },
  { lon: 79.535, lat: 30.535, tier: 'STABLE', name: 'KM 0.00–0.25' },
  { lon: 79.6, lat: 30.575, tier: 'WEAK', name: 'KM 6.50–6.75' },
]

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function along(t: number): [number, number] {
  const scaled = t * (ROAD.length - 1)
  const i = Math.min(ROAD.length - 2, Math.floor(scaled))
  const f = scaled - i
  return [lerp(ROAD[i]![0], ROAD[i + 1]![0], f), lerp(ROAD[i]![1], ROAD[i + 1]![1], f)]
}

function scatter() {
    const features = Array.from({ length: 72 }, (_, i) => {
    const t = i / 71
    const [lon, lat] = along(t)
    const j = ((i * 17) % 9) - 4
    const k = ((i * 13) % 7) - 3
    const hot = t > 0.28 && t < 0.52
    const tier = hot ? (t > 0.36 && t < 0.44 ? 'CRITICAL' : 'ELEVATED') : t > 0.7 ? 'STABLE' : t > 0.55 ? 'WATCH' : 'STABLE'
    return {
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [lon + j * 0.00022, lat + k * 0.00016] },
      properties: { tier },
    }
  })
  return { type: 'FeatureCollection' as const, features }
}

function sitesFc() {
  return {
    type: 'FeatureCollection' as const,
    features: SITES.map((s) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] },
      properties: { tier: s.tier, name: s.name },
    })),
  }
}

const corridorFc = {
  type: 'FeatureCollection' as const,
  features: [
    {
      type: 'Feature' as const,
      geometry: { type: 'LineString' as const, coordinates: ROAD },
      properties: { worst_tier: 'CRITICAL' },
    },
  ],
}

const tierColor = ['match', ['get', 'tier'], ...Object.entries(TIER_HEX).flat(), TIER_HEX.WEAK] as unknown as maplibregl.ExpressionSpecification

const EMPTY = { type: 'FeatureCollection', features: [] } as const

/** Decorative map for the sign-in page: real satellite imagery, demonstration sites. Not authenticated data. */
export default function LoginMap() {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!el.current) return
    const map = new maplibregl.Map({
      container: el.current,
      style: SATELLITE_STYLE,
      center: [79.562, 30.548],
      zoom: 12.6,
      minZoom: 11,
      maxZoom: 15,
      dragRotate: false,
      pitchWithRotate: false,
      keyboard: false,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right')

    map.on('load', () => {
      map.addSource('corridor', { type: 'geojson', data: corridorFc as never })
      map.addSource('insar', { type: 'geojson', data: scatter() as never })
      map.addSource('sites', { type: 'geojson', data: sitesFc() as never })
      map.addSource('focus', { type: 'geojson', data: EMPTY as never })

      map.addLayer({
        id: 'corridor-casing',
        type: 'line',
        source: 'corridor',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#0f1419', 'line-opacity': 0.75, 'line-width': 8 },
      })
      map.addLayer({
        id: 'corridor',
        type: 'line',
        source: 'corridor',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': TIER_HEX.CRITICAL, 'line-width': 3.5 },
      })
      map.addLayer({
        id: 'insar',
        type: 'circle',
        source: 'insar',
        paint: {
          'circle-color': tierColor,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 3.2, 15, 5.5],
          'circle-opacity': 0.9,
          'circle-stroke-color': '#0f1419',
          'circle-stroke-width': 0.7,
        },
      })
      map.addLayer({
        id: 'sites',
        type: 'circle',
        source: 'sites',
        paint: {
          'circle-color': tierColor,
          'circle-radius': ['match', ['get', 'tier'], 'CRITICAL', 11, 'ELEVATED', 9, 7],
          'circle-stroke-color': '#e8eef4',
          'circle-stroke-width': 1.6,
        },
      })
      map.addLayer({
        id: 'focus',
        type: 'circle',
        source: 'focus',
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': 20,
          'circle-stroke-color': '#e8eef4',
          'circle-stroke-width': 2.4,
        },
      })
      ;(map.getSource('focus') as maplibregl.GeoJSONSource).setData({
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [79.56, 30.545] },
            properties: {},
          },
        ],
      } as never)
    })

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(el.current)
    return () => {
      ro.disconnect()
      map.remove()
    }
  }, [])

  return <div ref={el} className="login-map" role="img" aria-label="Satellite map of a mountain road with sites coloured by risk. Illustration." />
}
