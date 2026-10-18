import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import * as maplibregl from 'maplibre-gl'
// Vite's dependency optimizer breaks MapLibre's implicit worker lookup; point it at the file explicitly.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { Layers, LocateFixed } from 'lucide-react'
import { api } from '../api/client'
import type { SiteSummary } from '../api/types'
import { TIER_HEX, TIER_LABEL, TIER_ORDER } from '../lib/tier'
import { useUi, zoomLevelName } from '../store'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

// Esri World Imagery. Confirm the basemap's terms of use before any commercial deployment.
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

const POINT_MIN_ZOOM = 12.5
const STABLE_SITE_MIN_ZOOM = 11
const EMPTY = { type: 'FeatureCollection', features: [] } as const

type FC = { type: 'FeatureCollection'; features: unknown[] }

// Risk colour is data-driven from the tier property; these expressions are the single mapping.
const tierColor = [
  'match',
  ['get', 'tier'],
  ...Object.entries(TIER_HEX).flat(),
  TIER_HEX.WEAK,
] as unknown as maplibregl.ExpressionSpecification
const corridorColor = [
  'match',
  ['get', 'worst_tier'],
  ...Object.entries(TIER_HEX).flat(),
  TIER_HEX.STABLE,
] as unknown as maplibregl.ExpressionSpecification
const siteRadius = [
  'match',
  ['get', 'tier'],
  'CRITICAL', 13,
  'ELEVATED', 10,
  'WATCH', 8,
  'WEAK', 8,
  5,
] as unknown as maplibregl.ExpressionSpecification

// Higher sort key draws on top: a lower tier must never hide a higher one where markers overlap.
const siteSortKey = [
  'match',
  ['get', 'tier'],
  'CRITICAL', 4,
  'ELEVATED', 3,
  'WATCH', 2,
  'WEAK', 1,
  0,
] as unknown as maplibregl.ExpressionSpecification

function viewBox(map: maplibregl.Map): [number, number, number, number] {
  const b = map.getBounds()
  return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
}

function pointFeature(lon: number, lat: number, properties: Record<string, unknown>) {
  return { type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties }
}

export function MapView() {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)

  const regionId = useUi((s) => s.regionId)
  const selectedId = useUi((s) => s.selectedSiteId)
  const select = useUi((s) => s.selectSite)
  const setView = useUi((s) => s.setView)
  const zoom = useUi((s) => s.zoom)
  const bbox = useUi((s) => s.bbox)
  const showPoints = useUi((s) => s.showPoints)
  const showCorridors = useUi((s) => s.showCorridors)
  const toggle = useUi((s) => s.toggle)

  const { data: regions } = useQuery({ queryKey: ['regions'], queryFn: api.regions })
  const { data: corridors } = useQuery({ queryKey: ['corridors', regionId], queryFn: () => api.corridors(regionId) })
  const { data: sitesData } = useQuery({ queryKey: ['sites', regionId], queryFn: () => api.sites(regionId) })

  // Raw scatterers: only in a site-level viewport, never the full dataset.
  const roundedBox = bbox?.map((v) => Math.round(v * 200) / 200) as typeof bbox
  const { data: pointsData } = useQuery({
    queryKey: ['points', roundedBox],
    queryFn: () => api.points(roundedBox!),
    enabled: !!roundedBox && zoom >= POINT_MIN_ZOOM && showPoints,
    placeholderData: (prev) => prev,
  })

  const sites = useMemo(() => sitesData?.sites ?? [], [sitesData])
  const selected: SiteSummary | null = sites.find((s) => s.site_id === selectedId) ?? null

  // The click handler is registered once; keep the latest `select` reachable without re-registering.
  const selectRef = useRef(select)
  useEffect(() => {
    selectRef.current = select
  }, [select])

  // --- map init (once) ---
  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: SATELLITE_STYLE,
      center: [79, 22],
      zoom: 4,
      maxZoom: 18.5,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right')

    map.on('load', () => {
      for (const id of ['corridors', 'insar', 'sites', 'selected']) {
        map.addSource(id, { type: 'geojson', data: EMPTY as never })
      }
      // dark casing keeps the risk colour legible on both bright desert and dark forest imagery
      map.addLayer({
        id: 'corridors-casing',
        type: 'line',
        source: 'corridors',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#0f1419', 'line-opacity': 0.7, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 4, 14, 9] },
      })
      map.addLayer({
        id: 'corridors',
        type: 'line',
        source: 'corridors',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': corridorColor, 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 2, 14, 5] },
      })
      map.addLayer({
        id: 'insar',
        type: 'circle',
        source: 'insar',
        minzoom: POINT_MIN_ZOOM,
        paint: {
          'circle-color': tierColor,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12.5, 3, 17, 6],
          'circle-opacity': 0.9,
          'circle-stroke-color': '#0f1419',
          'circle-stroke-width': 0.75,
        },
      })
      const siteStyle = {
        'circle-color': tierColor,
        'circle-radius': siteRadius,
        'circle-opacity': 0.95,
        'circle-stroke-color': '#e8eef4',
        'circle-stroke-width': 1.5,
      }
      map.addLayer({
        id: 'sites-stable',
        type: 'circle',
        source: 'sites',
        minzoom: STABLE_SITE_MIN_ZOOM,
        filter: ['==', ['get', 'tier'], 'STABLE'],
        paint: siteStyle,
      })
      map.addLayer({
        id: 'sites-main',
        type: 'circle',
        source: 'sites',
        filter: ['!=', ['get', 'tier'], 'STABLE'],
        layout: { 'circle-sort-key': siteSortKey },
        paint: siteStyle,
      })
      map.addLayer({
        id: 'selected',
        type: 'circle',
        source: 'selected',
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': 22,
          'circle-stroke-color': '#e8eef4',
          'circle-stroke-width': 2.5,
        },
      })

      const clickable = ['sites-main', 'sites-stable']
      map.on('click', clickable, (e) => {
        const id = e.features?.[0]?.properties?.site_id as string | undefined
        if (id) selectRef.current(id, 'now')
      })
      map.on('mouseenter', clickable, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', clickable, () => (map.getCanvas().style.cursor = ''))
      setReady(true)
    })

    const sync = () => setView(viewBox(map), map.getZoom())
    map.on('moveend', sync)
    map.once('load', sync)
    mapRef.current = map
    // Dev-only handle for browser-driven verification; Vite strips this from production builds.
    if (import.meta.env.DEV) Object.assign(window, { __ts: { map } })

    return () => {
      map.remove()
      mapRef.current = null
      setReady(false)
    }
  }, [setView])

  const setData = (id: string, data: unknown) =>
    (mapRef.current?.getSource(id) as maplibregl.GeoJSONSource | undefined)?.setData(data as never)

  // --- data -> sources ---
  useEffect(() => {
    if (ready) setData('corridors', corridors ?? EMPTY)
  }, [ready, corridors])

  useEffect(() => {
    if (!ready) return
    setData('sites', {
      type: 'FeatureCollection',
      features: sites.map((s) => pointFeature(s.lon, s.lat, { site_id: s.site_id, tier: s.tier })),
    } satisfies FC)
  }, [ready, sites])

  useEffect(() => {
    if (!ready) return
    const pts = showPoints && pointsData ? pointsData.points : []
    setData('insar', {
      type: 'FeatureCollection',
      features: pts.map((p) => pointFeature(p.lon, p.lat, { tier: p.tier })),
    } satisfies FC)
  }, [ready, pointsData, showPoints])

  useEffect(() => {
    if (!ready) return
    setData('selected', {
      type: 'FeatureCollection',
      features: selected ? [pointFeature(selected.lon, selected.lat, { site_id: selected.site_id })] : [],
    } satisfies FC)
  }, [ready, selected])

  // --- layer toggle ---
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const vis = showCorridors ? 'visible' : 'none'
    map.setLayoutProperty('corridors', 'visibility', vis)
    map.setLayoutProperty('corridors-casing', 'visibility', vis)
  }, [ready, showCorridors])

  // --- fly to region ---
  useEffect(() => {
    const r = regions?.find((x) => x.region_id === regionId)
    if (r && mapRef.current) mapRef.current.flyTo({ center: r.center, zoom: r.zoom, duration: 900 })
  }, [regionId, regions])

  // --- fly to an explicit target (search results, "view on map" buttons) ---
  const mapTarget = useUi((s) => s.mapTarget)
  useEffect(() => {
    if (ready && mapTarget && mapRef.current) {
      mapRef.current.flyTo({ center: mapTarget.center, zoom: mapTarget.zoom, duration: 800 })
    }
  }, [ready, mapTarget])

  // --- fly to selected site ---
  useEffect(() => {
    if (selected && mapRef.current) {
      mapRef.current.flyTo({
        center: [selected.lon, selected.lat],
        zoom: Math.max(mapRef.current.getZoom(), 14.5),
        duration: 700,
      })
    }
  }, [selected?.site_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const fitRegion = () => {
    const r = regions?.find((x) => x.region_id === regionId)
    if (r) mapRef.current?.flyTo({ center: r.center, zoom: r.zoom, duration: 700 })
  }

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />

      <div className="map-controls">
        <button className="map-btn" onClick={fitRegion} title="Fit region">
          <LocateFixed size={15} /> Fit region
        </button>
        <div className="map-toggles">
          <Layers size={14} className="muted" />
          <label>
            <input type="checkbox" checked={showCorridors} onChange={() => toggle('showCorridors')} /> Corridors
          </label>
          <label>
            <input type="checkbox" checked={showPoints} onChange={() => toggle('showPoints')} /> InSAR points
          </label>
        </div>
      </div>

      <div className="legend" aria-label="Legend">
        {TIER_ORDER.map((t) => (
          <span key={t} className="legend-item">
            <i style={{ background: TIER_HEX[t] }} /> {TIER_LABEL[t]}
          </span>
        ))}
      </div>

      <div className="zoom-hud mono">
        {zoomLevelName(zoom)} · z{zoom.toFixed(1)}
        {zoom < POINT_MIN_ZOOM && showPoints && <span className="muted"> · zoom in for InSAR points</span>}
      </div>
    </div>
  )
}
