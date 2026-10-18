import { useEffect, useId, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, MapPin, Route, Search } from 'lucide-react'
import { api } from '../api/client'
import type { SearchResult } from '../api/types'
import { navigate } from '../lib/router'
import { useUi } from '../store'

const ICON = { region: MapPin, asset: Route, site: Building2 } as const

export function GlobalSearch() {
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  const listId = useId()
  const setRegion = useUi((s) => s.setRegion)
  const selectSite = useUi((s) => s.selectSite)
  const flyTo = useUi((s) => s.flyTo)
  const selectAsset = useUi((s) => s.selectAsset)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 180)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // "/" focuses search from anywhere
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') {
        e.preventDefault()
        input.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api.search(debounced),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  })
  const results = data?.results ?? []

  const pick = (r: SearchResult) => {
    setOpen(false)
    setQ('')
    if (r.type === 'region') {
      setRegion(r.id)
      navigate('/')
      flyTo([r.lon, r.lat], r.zoom)
    } else if (r.type === 'site') {
      navigate('/')
      selectSite(r.id, 'now')
      flyTo([r.lon, r.lat], 14.5)
    } else {
      navigate('/corridors')
      flyTo([r.lon, r.lat], r.zoom)
      selectAsset(r.id)
    }
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (!open || !results.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a - 1 + results.length) % results.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="search" ref={box}>
      <Search size={15} className="search-icon" aria-hidden />
      <input
        ref={input}
        type="search"
        role="combobox"
        aria-expanded={open && debounced.length >= 2}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${listId}-${active}` : undefined}
        placeholder="Search sites, assets, regions   ( / )"
        aria-label="Search sites, assets and regions"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      {open && debounced.length >= 2 && (
        <ul className="search-pop" role="listbox" id={listId}>
          {results.length === 0 && <li className="search-none">{isFetching ? 'Searching...' : `No match for "${debounced}"`}</li>}
          {results.map((r, i) => {
            const Icon = ICON[r.type]
            return (
              <li key={`${r.type}-${r.id}`} id={`${listId}-${i}`} role="option" aria-selected={i === active} className={i === active ? 'on' : ''} onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(r) }}>
                <Icon size={14} aria-hidden />
                <span className="search-main">
                  <span>{r.title}</span>
                  <span className="muted">{r.subtitle}</span>
                </span>
                <span className="search-type">{r.type}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
