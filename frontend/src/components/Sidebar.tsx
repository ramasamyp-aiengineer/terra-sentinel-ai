import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api } from '../api/client'
import { BrandWordmark } from './brand/BrandLogo'
import { GROUPS, NAV, navigate, useRoute } from '../lib/router'
import { useAuth } from '../lib/auth'
import { useUi } from '../store'

export function Sidebar() {
  const route = useRoute()
  const regionId = useUi((s) => s.regionId)
  const navOpen = useUi((s) => s.navOpen)
  const setNavOpen = useUi((s) => s.setNavOpen)
  const { data: alerts } = useQuery({ queryKey: ['alerts', regionId, '', ''], queryFn: () => api.alerts(regionId), staleTime: 30_000 })
  const { can } = useAuth()
  const visible = NAV.filter((n) => !n.role || can(n.role))

  return (
    <>
      {navOpen && <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden />}
      <nav className={`sidebar ${navOpen ? 'open' : ''}`} aria-label="Main navigation">
        <div className="brand">
          <BrandWordmark tagline="Ground-motion early warning" />
          <button className="icon-btn sidebar-close" onClick={() => setNavOpen(false)} aria-label="Close menu">
            <X size={16} />
          </button>
        </div>

        <div className="nav-scroll">
          {GROUPS.filter((g) => visible.some((n) => n.group === g)).map((g) => (
            <div key={g} className="nav-group">
              <div className="nav-group-label">{g}</div>
              {visible.filter((n) => n.group === g).map((n) => {
                const Icon = n.icon
                const active = route === n.path
                const badge = n.path === '/alerts' ? alerts?.summary.open_critical : 0
                return (
                  <a
                    key={n.path}
                    href={`#${n.path}`}
                    className={`nav-item ${active ? 'active' : ''}`}
                    aria-current={active ? 'page' : undefined}
                    onClick={() => {
                      setNavOpen(false)
                      navigate(n.path)
                    }}
                    title={n.blurb}
                  >
                    <Icon size={17} strokeWidth={1.9} aria-hidden />
                    <span>{n.label}</span>
                    {badge ? (
                      <span className="nav-badge mono" aria-label={`${badge} critical alerts open`}>
                        {badge}
                      </span>
                    ) : null}
                  </a>
                )
              })}
            </div>
          ))}
        </div>

        <div className="sidebar-foot">
          Decision support for qualified engineers. Outlooks are bands that assume today's trend continues, not predictions of failure.
        </div>
      </nav>
    </>
  )
}
