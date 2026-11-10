import type {
  DriverView, ImportResult, Me, Place, Plan, PlanPatch, PlanSummary, RegisterRequest, Settings, StopStatus,
} from './types.ts'

/** Сессия закончилась или её нет — нужно показать экран входа. */
export class AuthError extends Error {}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: 'same-origin', ...options })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? 'Проверьте заполнение полей'
          : 'Сервер не ответил, попробуйте ещё раз'
    if (res.status === 401 && !url.startsWith('/api/auth/')) {
      onUnauthorized()
      throw new AuthError(message)
    }
    throw new Error(message)
  }
  return data as T
}

const send = <T>(method: string, url: string, body?: unknown) =>
  request<T>(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
const post = <T>(url: string, body?: unknown) => send<T>('POST', url, body)

// ---------- Вход ----------

/** null — не вошли. */
export const fetchMe = async (): Promise<Me | null> => {
  const res = await fetch('/api/auth/me', { credentials: 'same-origin' })
  if (res.status === 401) return null
  if (!res.ok) throw new Error('Сервер не ответил, попробуйте обновить страницу')
  return res.json()
}

export const login = (email: string, password: string) => post<Me>('/api/auth/login', { email, password })
export const register = (data: RegisterRequest) => post<Me>('/api/auth/register', data)
export const logout = () => post<{ ok: boolean }>('/api/auth/logout')

// ---------- Склад и настройки компании ----------

export const getSettings = () => request<Settings>('/api/company/settings')
export const patchSettings = (patch: Partial<Settings> & { clear_depot?: boolean }) =>
  send<Settings>('PATCH', '/api/company/settings', patch)

// ---------- Маршрутные листы ----------

export const listPlans = () => request<PlanSummary[]>('/api/plans')
export const getPlan = (id: number) => request<Plan>(`/api/plans/${id}`)
export const createPlan = (body: { plan_date: string; stops?: Place[]; from_plan_id?: number }) =>
  post<Plan>('/api/plans', body)
export const patchPlan = (id: number, patch: PlanPatch) => send<Plan>('PATCH', `/api/plans/${id}`, patch)
export const deletePlan = (id: number) => send<{ ok: boolean }>('DELETE', `/api/plans/${id}`)
export const buildPlan = (id: number) => post<Plan>(`/api/plans/${id}/build`)
export const getStatuses = (id: number) => request<Record<string, StopStatus>>(`/api/plans/${id}/statuses`)

// ---------- Импорт из Excel / CSV / вставленного текста ----------

export const importPoints = (body: Blob | string, kind: 'file' | 'text') =>
  request<ImportResult>(`/api/import?kind=${kind}`, { method: 'POST', body })

// ---------- Страница водителя (без входа) ----------

export const getDriverRoute = (token: string) => request<DriverView>(`/api/driver/${encodeURIComponent(token)}`)
export const setDriverStatus = (token: string, index: number, status: StopStatus | null) =>
  send<DriverView>('PUT', `/api/driver/${encodeURIComponent(token)}/stops/${index}`, { status })

// ---------- Поиск адресов ----------

export const geocode = (q: string) => request<Place[]>(`/api/geocode?q=${encodeURIComponent(q)}`)
