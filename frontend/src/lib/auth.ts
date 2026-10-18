import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, UNAUTHORIZED_EVENT } from '../api/client'
import type { AuthMe, Role } from '../api/types'
import { useUi } from '../store'

const RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 }
const KEY = ['auth'] as const

export interface Auth {
  loading: boolean
  /** Could not reach the API at all (as opposed to "not signed in"). */
  unreachable: boolean
  authEnabled: boolean
  user: AuthMe['user']
  expired: boolean
  passwordMin: number
  /** True when the signed-in user holds at least `role`. */
  can: (role: Role) => boolean
}

export function useAuth(): Auth {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: KEY, queryFn: api.me, staleTime: Infinity, retry: 1, refetchOnWindowFocus: false })

  // The server tells us (any 401) that the session ended while the app was open.
  useEffect(() => {
    const onLost = () => {
      qc.setQueryData<AuthMe>(KEY, (old) => (old && old.auth_enabled ? { ...old, user: null, expired: true } : old))
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onLost)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onLost)
  }, [qc])

  const me = q.data
  const user = me?.user ?? null
  return {
    loading: q.isLoading,
    unreachable: !q.data && q.isError,
    authEnabled: me?.auth_enabled ?? true,
    user,
    expired: !!me?.expired,
    passwordMin: me?.password_min_length ?? 10,
    can: (role) => !!user && RANK[user.role] >= RANK[role],
  }
}

/** Shorthand for components that only need to know whether an action is allowed. */
export function useCan(role: Role): boolean {
  return useAuth().can(role)
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) => api.login(username, password),
    onSuccess: async () => {
      qc.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' }) // nothing from a previous session survives
      await qc.invalidateQueries({ queryKey: KEY })
    },
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.logout,
    onSettled: async () => {
      qc.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' }) // drop every cached record before the next person signs in
      useUi.getState().selectSite(null)
      await qc.invalidateQueries({ queryKey: KEY })
      window.location.hash = '/'
    },
  })
}
