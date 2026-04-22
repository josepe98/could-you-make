import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { listApps } from './api.js'

const AppsContext = createContext({
  apps: [],
  appLabels: {},
  loading: true,
  error: null,
  refresh: () => {},
})

export function AppsProvider({ children }) {
  const [apps, setApps] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listApps()
      setApps(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const appLabels = useMemo(
    () => Object.fromEntries(apps.map(a => [a.slug, a.label])),
    [apps],
  )

  const value = useMemo(
    () => ({ apps, appLabels, loading, error, refresh }),
    [apps, appLabels, loading, error, refresh],
  )

  return <AppsContext.Provider value={value}>{children}</AppsContext.Provider>
}

export function useApps() {
  return useContext(AppsContext)
}
