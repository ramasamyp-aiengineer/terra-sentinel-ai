import { Component, lazy, Suspense, useEffect, type ReactNode } from 'react'
import { SiteDrawer } from './components/SiteDrawer'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { Btn, Empty, Loading } from './components/ui'
import { LoginPage } from './pages/LoginPage'
import { useAuth } from './lib/auth'
import { navItemFor, useRoute } from './lib/router'
import { useQueryClient } from '@tanstack/react-query'
import { ShieldOff } from 'lucide-react'
import { useUrlState } from './lib/urlState'
import './App.css'

const PAGES: Record<string, ReturnType<typeof lazy>> = {
  '/': lazy(() => import('./pages/CommandCenter')),
  '/alerts': lazy(() => import('./pages/AlertsPage')),
  '/brief': lazy(() => import('./pages/BriefPage')),
  '/early-warning': lazy(() => import('./pages/EarlyWarningPage')),
  '/trends': lazy(() => import('./pages/TrendsPage')),
  '/corridors': lazy(() => import('./pages/CorridorsPage')),
  '/portfolio': lazy(() => import('./pages/PortfolioPage')),
  '/workorders': lazy(() => import('./pages/WorkOrdersPage')),
  '/data': lazy(() => import('./pages/DataHubPage')),
  '/access': lazy(() => import('./pages/AccessPage')),
  '/methodology': lazy(() => import('./pages/MethodologyPage')),
}

class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="page">
        <div className="error-box" role="alert">
          <div>
            <strong>This page failed to display</strong>
            <p>{this.state.error.message}</p>
          </div>
          <Btn small onClick={() => this.setState({ error: null })}>
            Try again
          </Btn>
        </div>
      </div>
    )
  }
}

/** Shows the sign-in page until the server confirms a session, then the workspace. No flash of app content. */
export default function App() {
  const auth = useAuth()
  const qc = useQueryClient()
  if (auth.loading) {
    return (
      <div className="fullscreen-state">
        <Loading label="Starting TerraSentinel" />
      </div>
    )
  }
  if (auth.authEnabled && !auth.user) {
    return <LoginPage expired={auth.expired} unreachable={auth.unreachable} onRetry={() => qc.invalidateQueries({ queryKey: ['auth'] })} />
  }
  return <Workspace />
}

function Workspace() {
  useUrlState()
  const route = useRoute()
  const { can } = useAuth()
  const item = navItemFor(route)
  const allowed = !item.role || can(item.role)
  const Page = PAGES[item.path] ?? PAGES['/']

  useEffect(() => {
    document.title = `${item.label} · TerraSentinel`
  }, [item.label])

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Sidebar />
      <div className="app-body">
        <TopBar />
        <main id="main" className={`main ${item.path === '/' ? 'main-map' : 'main-scroll'}`} tabIndex={-1}>
          <Boundary key={route}>
            <Suspense fallback={<div className="page"><Loading /></div>}>
              {allowed ? <Page /> : <div className="page"><Empty icon={ShieldOff} title="Not available for your role">Ask an administrator if you need access to {item.label}.</Empty></div>}
            </Suspense>
          </Boundary>
        </main>
      </div>
      <SiteDrawer />
    </div>
  )
}
