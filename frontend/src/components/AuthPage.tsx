import { useState, type FormEvent } from 'react'
import { login, register } from '../api.ts'
import type { Me } from '../types.ts'

type Mode = 'login' | 'register'

const EyeIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)

const EyeOffIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.6 5.1A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-2.9 3.9M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    <path d="m3 3 18 18" />
  </svg>
)

export default function AuthPage({ onDone }: { onDone: (me: Me) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [company, setCompany] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const switchMode = (m: Mode) => {
    setMode(m)
    setError('')
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (mode === 'register' && password.length < 8) {
      setError('Пароль — минимум 8 символов')
      return
    }
    setBusy(true)
    setError('')
    try {
      onDone(mode === 'login' ? await login(email, password) : await register({ company, name, email, password }))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <form className="auth__card glass" onSubmit={submit}>
        <header className="panel__head">
          <h1>Маршруты</h1>
          <p className="muted">Простые маршруты для ваших машин — за пару минут в день.</p>
        </header>

        <div className="segmented auth__tabs">
          <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>
            Вход
          </button>
          <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>
            Регистрация
          </button>
        </div>

        {mode === 'register' && (
          <>
            <label className="input">
              <span>Название компании</span>
              <input value={company} onChange={(e) => setCompany(e.target.value)} required minLength={2} autoComplete="organization" />
            </label>
            <label className="input">
              <span>Ваше имя</span>
              <input value={name} onChange={(e) => setName(e.target.value)} required autoComplete="name" />
            </label>
          </>
        )}

        <label className="input">
          <span>Email</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <div className="input">
          <label htmlFor="auth-password">Пароль</label>
          <span className="password">
            <input
              id="auth-password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === 'register' ? 8 : undefined}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder={mode === 'register' ? 'Минимум 8 символов' : undefined}
              spellCheck={false}
              autoCapitalize="off"
            />
            <button
              type="button"
              className="password__toggle"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
              aria-pressed={showPassword}
              title={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
            >
              {showPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </span>
        </div>

        {error && <p className="notice notice--error">{error}</p>}

        <button className="btn btn--primary btn--big btn--wide" disabled={busy}>
          {busy ? 'Секунду…' : mode === 'login' ? 'Войти' : 'Создать компанию'}
        </button>

        <p className="hint auth__switch">
          {mode === 'login' ? (
            <>
              Ещё нет аккаунта?{' '}
              <button type="button" className="link" onClick={() => switchMode('register')}>
                Зарегистрируйте компанию
              </button>
            </>
          ) : (
            <>
              Уже зарегистрированы?{' '}
              <button type="button" className="link" onClick={() => switchMode('login')}>
                Войдите
              </button>
            </>
          )}
        </p>
      </form>
    </div>
  )
}
