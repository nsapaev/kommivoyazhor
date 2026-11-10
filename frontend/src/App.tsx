import { useEffect, useState } from 'react'
import { fetchMe, logout, setUnauthorizedHandler } from './api.ts'
import AuthPage from './components/AuthPage.tsx'
import DriverPage from './components/DriverPage.tsx'
import Planner from './components/Planner.tsx'
import type { Me } from './types.ts'

/** /d/<token> — страница водителя: без входа, по секретной ссылке. */
const driverToken = window.location.pathname.match(/^\/d\/([\w-]+)\/?$/)?.[1] ?? null

export default function App() {
  return (
    <>
      <div className="backdrop" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>
      {driverToken ? <DriverPage token={driverToken} /> : <Office />}
    </>
  )
}

// undefined — ещё проверяем сессию, null — не вошли.
function Office() {
  const [me, setMe] = useState<Me | null | undefined>(undefined)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    setUnauthorizedHandler(() => setMe(null))
    fetchMe()
      .then(setMe)
      .catch((e: Error) => setLoadError(e.message))
  }, [])

  const doLogout = async () => {
    await logout().catch(() => {})
    setMe(null)
  }

  return (
    <>
      {loadError ? (
        <div className="auth">
          <p className="notice notice--error">{loadError}</p>
        </div>
      ) : me === undefined ? null : me ? (
        <Planner key={me.company_id} me={me} onLogout={doLogout} />
      ) : (
        <AuthPage onDone={setMe} />
      )}
    </>
  )
}
