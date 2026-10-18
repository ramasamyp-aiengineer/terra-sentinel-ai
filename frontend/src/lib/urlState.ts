import { useEffect } from 'react'
import { useUi } from '../store'

/**
 * Keeps the scope of a view (region + open site) in the URL hash so any view can be linked or reloaded:
 *   #/early-warning?region=IN-TN&site=METRO4-DEMO-004
 * The page path stays owned by lib/router.ts; this only manages the query part.
 *
 * - Region is a global scope: it survives navigation, the URL follows the store.
 * - The open site is part of the view: the URL wins, so following a link opens it and navigating away closes it.
 */
const DEFAULT_REGION = 'IN'

function parse() {
  const raw = window.location.hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')
  return { path: path || '/', params: new URLSearchParams(query) }
}

function write() {
  const { regionId, selectedSiteId } = useUi.getState()
  const { path, params } = parse()
  if (regionId !== DEFAULT_REGION) params.set('region', regionId)
  else params.delete('region')
  if (selectedSiteId) params.set('site', selectedSiteId)
  else params.delete('site')
  const q = params.toString()
  const next = `#${path}${q ? `?${q}` : ''}`
  if (next !== window.location.hash) window.history.replaceState(null, '', next) // no history spam, no hashchange loop
}

function read() {
  const { params } = parse()
  const st = useUi.getState()
  const region = params.get('region')
  const site = params.get('site')
  if (region && region !== st.regionId) st.setRegion(region)
  if (site !== useUi.getState().selectedSiteId) st.selectSite(site)
  write()
}

export function useUrlState() {
  useEffect(() => {
    read()
    window.addEventListener('hashchange', read)
    const unsub = useUi.subscribe((s, prev) => {
      if (s.regionId !== prev.regionId || s.selectedSiteId !== prev.selectedSiteId) write()
    })
    return () => {
      window.removeEventListener('hashchange', read)
      unsub()
    }
  }, [])
}
