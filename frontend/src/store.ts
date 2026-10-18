import { create } from 'zustand'

export type DrawerTab = 'now' | 'trend' | 'history' | 'outlook' | 'action'

export interface MapTarget {
  center: [number, number]
  zoom: number
  nonce: number
}

interface UiState {
  regionId: string
  selectedSiteId: string | null
  selectedAssetId: string | null
  tab: DrawerTab
  bbox: [number, number, number, number] | null
  zoom: number
  showPoints: boolean
  showCorridors: boolean
  mapTarget: MapTarget | null
  navOpen: boolean
  setRegion: (id: string) => void
  selectSite: (id: string | null, tab?: DrawerTab) => void
  selectAsset: (id: string | null) => void
  setTab: (t: DrawerTab) => void
  setView: (bbox: [number, number, number, number], zoom: number) => void
  toggle: (k: 'showPoints' | 'showCorridors') => void
  flyTo: (center: [number, number], zoom: number) => void
  setNavOpen: (open: boolean) => void
}

export const useUi = create<UiState>((set) => ({
  regionId: 'IN',
  selectedSiteId: null,
  selectedAssetId: null,
  tab: 'now',
  bbox: null,
  zoom: 4,
  showPoints: true,
  showCorridors: true,
  mapTarget: null,
  navOpen: false,
  setRegion: (regionId) => set({ regionId, selectedSiteId: null }),
  selectSite: (selectedSiteId, tab = 'now') => set({ selectedSiteId, tab }),
  selectAsset: (selectedAssetId) => set({ selectedAssetId }),
  setTab: (tab) => set({ tab }),
  setView: (bbox, zoom) => set({ bbox, zoom }),
  toggle: (k) => set((s) => ({ [k]: !s[k] }) as Partial<UiState>),
  flyTo: (center, zoom) => set({ mapTarget: { center, zoom, nonce: Date.now() } }),
  setNavOpen: (navOpen) => set({ navOpen }),
}))

export function zoomLevelName(z: number): string {
  if (z < 7) return 'National view'
  if (z < 11) return 'Region view'
  if (z < 14) return 'Corridor view'
  return 'Site view'
}
