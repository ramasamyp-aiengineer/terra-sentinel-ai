import { useSyncExternalStore } from 'react'
import type { Role } from '../api/types'
import {
  BellRing,
  Building2,
  Database,
  FileText,
  Gauge,
  LayoutDashboard,
  LineChart,
  Route,
  ShieldCheck,
  Sunrise,
  Wrench,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  path: string
  label: string
  icon: LucideIcon
  group: 'Monitor' | 'Intelligence' | 'Operate' | 'Data' | 'Reference' | 'Admin'
  blurb: string
  /** Lowest role that sees this page. Omitted means everyone who is signed in. */
  role?: Role
}

/** One list drives the sidebar, the router and the page titles. */
export const NAV: NavItem[] = [
  { path: '/', label: 'Command Center', icon: LayoutDashboard, group: 'Monitor', blurb: 'Satellite map, ranked sites and what to do today' },
  { path: '/alerts', label: 'Alerts', icon: BellRing, group: 'Monitor', blurb: 'What changed since the last satellite pass' },
  { path: '/brief', label: 'Morning Brief', icon: Sunrise, group: 'Monitor', blurb: 'A one-page summary for the day' },
  { path: '/early-warning', label: 'Early Warning', icon: Gauge, group: 'Intelligence', blurb: 'Time-to-threshold outlook for moving sites' },
  { path: '/trends', label: 'Trends & History', icon: LineChart, group: 'Intelligence', blurb: 'How risk has evolved across satellite passes' },
  { path: '/corridors', label: 'Corridors', icon: Route, group: 'Intelligence', blurb: 'Every asset, chainage by chainage' },
  { path: '/portfolio', label: 'Portfolio', icon: Building2, group: 'Intelligence', blurb: 'Compare regions and asset types' },
  { path: '/workorders', label: 'Work Orders', icon: Wrench, group: 'Operate', blurb: 'Inspection tickets with grounded evidence' },
  { path: '/data', label: 'Data Hub', icon: Database, group: 'Data', blurb: 'Upload, link, fetch and manage the data behind everything' },
  { path: '/access', label: 'Users & access', icon: ShieldCheck, group: 'Admin', role: 'admin', blurb: 'Who can sign in, what they can do, and recent security activity' },
  { path: '/methodology', label: 'Methodology', icon: FileText, group: 'Reference', blurb: 'The rules, thresholds and limits of the analysis' },
]

export const GROUPS = ['Monitor', 'Intelligence', 'Operate', 'Data', 'Reference', 'Admin'] as const

function currentPath(): string {
  const raw = window.location.hash.replace(/^#/, '') || '/'
  return raw.split('?')[0] || '/'
}

function subscribe(cb: () => void) {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}

export function useRoute(): string {
  return useSyncExternalStore(subscribe, currentPath, () => '/')
}

export function navigate(path: string) {
  window.location.hash = path
}

export function navItemFor(path: string): NavItem {
  return NAV.find((n) => n.path === path) ?? NAV[0]
}
