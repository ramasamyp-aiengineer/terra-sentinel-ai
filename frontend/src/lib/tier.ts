import type { Tier } from '../api/types'

/** Map marker colours: tuned for contrast on satellite imagery. */
export const TIER_HEX: Record<Tier | 'UNMONITORED', string> = {
  CRITICAL: '#E5392B',
  ELEVATED: '#F28C1B',
  WATCH: '#F2C21B',
  STABLE: '#3FB36F',
  WEAK: '#9AA5B4',
  UNMONITORED: '#6B7A8C',
}

/** UI colours: tuned for a white background. Text on `fill` always meets 4.5:1 contrast. */
export const TIER_UI: Record<Tier, { fill: string; text: string; soft: string; strong: string }> = {
  CRITICAL: { fill: '#C62828', text: '#FFFFFF', soft: '#FDECEA', strong: '#A61E1E' },
  ELEVATED: { fill: '#B85209', text: '#FFFFFF', soft: '#FDF0E3', strong: '#9A4306' },
  WATCH: { fill: '#E3B100', text: '#1F2933', soft: '#FFF7DB', strong: '#7A5C00' },
  STABLE: { fill: '#2A7F4F', text: '#FFFFFF', soft: '#E6F4EC', strong: '#1F6A40' },
  WEAK: { fill: '#6B7785', text: '#FFFFFF', soft: '#EEF0F3', strong: '#4B5563' },
}

export const TIER_LABEL: Record<Tier, string> = {
  CRITICAL: 'Critical',
  ELEVATED: 'Elevated',
  WATCH: 'Watch',
  STABLE: 'Stable',
  WEAK: 'Data weak',
}

export const TIER_ORDER: Tier[] = ['CRITICAL', 'ELEVATED', 'WATCH', 'WEAK', 'STABLE']
export const TIER_RANK: Record<Tier, number> = { WEAK: -1, STABLE: 0, WATCH: 1, ELEVATED: 2, CRITICAL: 3 }

export const STATE_LABEL: Record<string, string> = {
  accelerating: 'Accelerating',
  threshold_approach: 'Approaching threshold',
  persistent_creep: 'Persistent creep',
  seasonal: 'Seasonal cycle',
  stable: 'Stable',
  data_degraded: 'Data degraded',
}

/** Fill is for marks and borders; text is the darker shade that keeps 4.5:1 contrast on soft. */
export const SEVERITY_UI: Record<string, { fill: string; soft: string; text: string; label: string }> = {
  critical: { fill: '#C62828', soft: '#FDECEA', text: '#B3261E', label: 'Critical' },
  high: { fill: '#B85209', soft: '#FDF0E3', text: '#9A4306', label: 'High' },
  medium: { fill: '#B58900', soft: '#FFF7DB', text: '#7A5C00', label: 'Medium' },
  info: { fill: '#3B6E8F', soft: '#E8F1F7', text: '#2F5D7C', label: 'Info' },
}
