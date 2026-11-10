import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import type { LatLng } from 'leaflet'
import {
  buildPlan,
  createPlan,
  deletePlan,
  getPlan,
  getSettings,
  getStatuses,
  listPlans,
  patchPlan,
  patchSettings,
} from '../api.ts'
import { todayISO } from '../dates.ts'
import { usePersistentState } from '../usePersistentState.ts'
import { useBottomSheet, useIsMobile } from '../useBottomSheet.ts'
import AddressSearch from './AddressSearch.tsx'
import BulkImport from './BulkImport.tsx'
import MapView from './MapView.tsx'
import PlanBar from './PlanBar.tsx'
import RouteCard from './RouteCard.tsx'
import StopEditor from './StopEditor.tsx'
import { windowText } from '../stops.ts'
import type { MapStyle, Me, Place, Plan, PlanPatch, PlanSummary, Settings } from '../types.ts'

const coordLabel = ({ lat, lng }: LatLng) => `Точка ${lat.toFixed(5)}, ${lng.toFixed(5)}`

const toSummary = ({ id, plan_date, status, stops_count, routes_count, total_km, updated_at }: Plan): PlanSummary => ({
  id, plan_date, status, stops_count, routes_count, total_km, updated_at,
})

/** Раньше склад и точки жили только в браузере — один раз переносим их на сервер. */
async function migrateLocalData(me: Me, settings: Settings, plans: PlanSummary[]): Promise<Settings> {
  const read = <T,>(key: string): T | null => {
    try {
      const v = localStorage.getItem(key)
      return v ? (JSON.parse(v) as T) : null
    } catch {
      return null
    }
  }
  const prefix = `c${me.company_id}:`
  const depot = read<Place>(`${prefix}depot`) ?? read<Place>('depot')
  const stops = read<Place[]>(`${prefix}stops`) ?? read<Place[]>('stops')

  if (depot && !settings.depot) settings = await patchSettings({ depot })
  if (stops?.length && !plans.length) await createPlan({ plan_date: todayISO(), stops })

  try {
    for (const k of ['depot', 'stops', 'vehicles', 'serviceMin', 'returnToDepot'])
      [k, prefix + k].forEach((key) => localStorage.removeItem(key))
  } catch {
    /* хранилище недоступно — не страшно */
  }
  return settings
}

interface Props {
  me: Me
  onLogout: () => void
}

export default function Planner({ me, onLogout }: Props) {
  const [mapStyle, setMapStyle] = usePersistentState<MapStyle>('mapStyle', 'scheme')
  const [lastPlanId, setLastPlanId] = usePersistentState<number | null>(`c${me.company_id}:planId`, null)

  const [settings, setSettings] = useState<Settings | null>(null)
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [plan, setPlanState] = useState<Plan | null>(null)

  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [bulkOpen, setBulkOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)

  const isMobile = useIsMobile()
  const sheet = useBottomSheet(isMobile)
  const resultsRef = useRef<HTMLElement>(null)

  // Последний лист в ref — чтобы правки, идущие подряд (вставка списка), не теряли друг друга.
  const planRef = useRef<Plan | null>(null)
  const setPlan = (p: Plan | null) => {
    planRef.current = p
    setPlanState(p)
  }
  // Сохранения уходят на сервер строго по очереди.
  const queue = useRef<Promise<unknown>>(Promise.resolve())
  const enqueue = <T,>(job: () => Promise<T>) => {
    const next = queue.current.then(job)
    queue.current = next.catch(() => {})
    return next
  }

  const upsertSummary = (p: Plan) =>
    setPlans((list) => {
      const s = toSummary(p)
      const rest = list.filter((x) => x.id !== s.id)
      return [s, ...rest].sort((a, b) => b.plan_date.localeCompare(a.plan_date) || b.id - a.id)
    })

  const openPlan = async (id: number) => {
    setError('')
    setBulkOpen(false)
    setEditing(null)
    try {
      const p = await enqueue(() => getPlan(id))
      setPlan(p)
      setLastPlanId(p.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const newPlan = async (fromPlanId?: number) => {
    setError('')
    setBulkOpen(false)
    setEditing(null)
    try {
      const p = await enqueue(() => createPlan({ plan_date: todayISO(), from_plan_id: fromPlanId }))
      upsertSummary(p)
      setPlan(p)
      setLastPlanId(p.id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const removePlan = async (id: number) => {
    setError('')
    try {
      await enqueue(() => deletePlan(id))
      const rest = plans.filter((p) => p.id !== id)
      setPlans(rest)
      if (planRef.current?.id === id) {
        if (rest.length) await openPlan(rest[0].id)
        else await newPlan()
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // Первая загрузка: склад, история, открыть последний лист (или создать на сегодня).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [s, list] = await Promise.all([getSettings(), listPlans()])
        const migrated = await migrateLocalData(me, s, list)
        const fresh = migrated !== s || !list.length ? await listPlans() : list
        if (cancelled) return
        setSettings(migrated)
        setPlans(fresh)
        const target = fresh.find((p) => p.id === lastPlanId) ?? fresh[0]
        if (target) {
          const p = await getPlan(target.id)
          if (!cancelled) setPlan(p)
        } else {
          const p = await createPlan({ plan_date: todayISO() })
          if (cancelled) return
          setPlans([toSummary(p)])
          setPlan(p)
          setLastPlanId(p.id)
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me.company_id])

  /** Правка листа: сразу на экране, следом — на сервер. Построенный маршрут сбрасывается. */
  const edit = (patch: PlanPatch) => {
    const cur = planRef.current
    if (!cur) return
    const stops = patch.stops ?? cur.stops
    const next: Plan = {
      ...cur, ...patch, stops, stops_count: stops.length,
      status: 'draft', result: null, routes_count: 0, total_km: 0,
    }
    setPlan(next)
    upsertSummary(next)
    setError('')
    enqueue(() => patchPlan(cur.id, patch)).catch((e: Error) => setError(e.message))
  }

  const addStops = (ps: Place[]) => edit({ stops: [...(planRef.current?.stops ?? []), ...ps] })
  const addStop = (p: Place) => addStops([p])
  const removeStop = (i: number) => {
    setEditing(null)
    edit({ stops: (planRef.current?.stops ?? []).filter((_, j) => j !== i) })
  }
  const saveStop = (i: number, p: Place) => {
    setEditing(null)
    edit({ stops: (planRef.current?.stops ?? []).map((s, j) => (j === i ? p : s)) })
  }
  const clearStops = () => {
    setEditing(null)
    edit({ stops: [] })
  }

  // Отметки водителей подтягиваем раз в 30 секунд, пока открыт построенный лист.
  const builtId = plan?.result ? plan.id : null
  useEffect(() => {
    if (builtId === null) return
    const tick = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const statuses = await getStatuses(builtId)
        const cur = planRef.current
        if (cur?.id === builtId && cur.result) setPlan({ ...cur, statuses })
      } catch {
        /* сеть мигнула — попробуем в следующий раз */
      }
    }
    const timer = setInterval(tick, 30_000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [builtId])

  const saveDepot = (depot: Place | null) => {
    setSettings((s) => (s ? { ...s, depot } : s))
    setError('')
    enqueue(() => patchSettings(depot ? { depot } : { clear_depot: true }))
      .then(setSettings)
      .catch((e: Error) => setError(e.message))
  }

  const onMapClick = (latlng: LatLng) => {
    if (!settings || !plan) return
    const place: Place = { label: coordLabel(latlng), lat: latlng.lat, lon: latlng.lng }
    if (settings.depot) addStop(place)
    else saveDepot(place)
  }

  const run = async () => {
    const cur = planRef.current
    if (!cur) return
    setBuilding(true)
    setError('')
    try {
      const built = await enqueue(() => buildPlan(cur.id))
      upsertSummary(built)
      if (planRef.current?.id === built.id) setPlan(built)
      // На телефоне раскрываем шторку на результатах
      if (isMobile) {
        if (sheet.snap === 0) sheet.setSnap(1)
        setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBuilding(false)
    }
  }

  const depot = settings?.depot ?? null
  const result = plan?.result ?? null
  const ready = !!settings && !!plan

  return (
    <div className="layout">
      <aside className={`panel glass${isMobile ? ' sheet' : ''}`} style={sheet.style}>
        {isMobile && (
          <div className="sheet__handle" {...sheet.handleProps} aria-label="Потяните, чтобы развернуть панель" role="button">
            <span />
          </div>
        )}
        <div className="panel__body">
        <div className="account">
          <span className="account__avatar">{me.company_name.trim()[0]?.toUpperCase()}</span>
          <span className="account__text">
            <strong>{me.company_name}</strong>
            <span className="muted">{me.name}</span>
          </span>
          <button className="link" onClick={onLogout}>
            Выйти
          </button>
        </div>

        {!ready ? (
          error ? <p className="notice notice--error">{error}</p> : <p className="hint">Загружаю маршруты…</p>
        ) : (
          <>
            <PlanBar
              current={toSummary(plan)}
              plans={plans}
              onOpen={openPlan}
              onNew={() => newPlan()}
              onRepeat={(id) => newPlan(id)}
              onDelete={removePlan}
            />

            <section>
              <h2>1. Склад</h2>
              {depot ? (
                <div className="chip">
                  <span className="chip__mark">С</span>
                  <span className="chip__text">{depot.label}</span>
                  <button className="link" onClick={() => saveDepot(null)}>
                    Изменить
                  </button>
                </div>
              ) : (
                <>
                  <AddressSearch placeholder="Адрес склада или офиса" onPick={saveDepot} />
                  <p className="hint">Или нажмите на карту. Склад общий для всех маршрутов.</p>
                </>
              )}
            </section>

            <section className={depot ? '' : 'is-disabled'}>
              <div className="section-head">
                <h2>
                  2. Куда едем {plan.stops.length > 0 && <span className="muted">· {plan.stops.length}</span>}
                </h2>
                {plan.stops.length > 0 && (
                  <button className="link" onClick={clearStops}>
                    Очистить
                  </button>
                )}
              </div>
              <AddressSearch placeholder="Адрес доставки" onPick={addStop} />
              {bulkOpen ? (
                <BulkImport onAdd={addStops} onClose={() => setBulkOpen(false)} />
              ) : (
                <p className="hint">
                  Или нажмите на карту, или{' '}
                  <button className="link" onClick={() => setBulkOpen(true)}>
                    вставьте список или загрузите Excel
                  </button>
                  .
                </p>
              )}
              {plan.stops.length > 0 && (
                <ol className="stops">
                  {plan.stops.map((s, i) =>
                    editing === i ? (
                      <li key={i} className="is-editing">
                        <StopEditor stop={s} onSave={(p) => saveStop(i, p)} onCancel={() => setEditing(null)} />
                      </li>
                    ) : (
                      <li key={i}>
                        <button className="stop-main" onClick={() => setEditing(i)} title="Телефон, время, комментарий">
                          <span className="stop-main__label">{s.label}</span>
                          {(windowText(s) || s.phone || s.comment) && (
                            <span className="stop-main__meta">
                              {windowText(s) && <span className="tw">{windowText(s)}</span>}
                              {s.phone && <span>{s.phone}</span>}
                              {s.comment && <span className="stop-main__comment">{s.comment}</span>}
                            </span>
                          )}
                        </button>
                        <button className="icon-btn" title="Убрать" onClick={() => removeStop(i)}>
                          ×
                        </button>
                      </li>
                    ),
                  )}
                </ol>
              )}
              {plan.stops.length > 0 && editing === null && (
                <p className="hint">Нажмите на точку, чтобы добавить телефон, время доставки или комментарий.</p>
              )}
            </section>

            <section className={depot ? '' : 'is-disabled'}>
              <h2>3. Настройки</h2>
              <div className="field">
                <span>Машин</span>
                <div className="segmented">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      className={n === plan.vehicles ? 'active' : ''}
                      onClick={() => n !== plan.vehicles && edit({ vehicles: n })}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
              <label className="field">
                <span>Минут на одну точку</span>
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={plan.service_min}
                  onChange={(e: ChangeEvent<HTMLInputElement>) =>
                    edit({ service_min: Math.max(0, Math.min(120, +e.target.value || 0)) })
                  }
                />
              </label>
              <label className="field">
                <span>Начало смены</span>
                <input
                  type="time"
                  value={plan.start_time}
                  onChange={(e) => e.target.value && edit({ start_time: e.target.value })}
                />
              </label>
              <label className="field field--check">
                <input
                  type="checkbox"
                  checked={plan.return_to_depot}
                  onChange={(e) => edit({ return_to_depot: e.target.checked })}
                />
                <span>Возвращаться на склад</span>
              </label>
            </section>

            <button
              className="btn btn--primary btn--big btn--wide"
              onClick={run}
              disabled={!depot || !plan.stops.length || building}
            >
              {building ? 'Считаю маршруты…' : result ? 'Пересчитать' : 'Построить маршруты'}
            </button>
            {error && <p className="notice notice--error">{error}</p>}

            {result && (
              <section className="results" ref={resultsRef}>
                {result.approximate && (
                  <p className="notice">
                    Сервер маршрутов был недоступен — порядок посчитан по прямой, время и километры примерные.
                  </p>
                )}
                {result.routes.map((r) => (
                  <RouteCard
                    key={r.vehicle}
                    route={r}
                    planDate={plan.plan_date}
                    statuses={plan.statuses ?? {}}
                    startTime={result.start_time}
                  />
                ))}
              </section>
            )}
          </>
        )}
        </div>
      </aside>

      <main className="map-wrap">
        <MapView
          depot={result?.depot ?? depot}
          stops={plan?.stops ?? []}
          routes={result?.routes}
          mapStyle={mapStyle}
          onMapStyleChange={setMapStyle}
          onMapClick={onMapClick}
          bottomInset={sheet.inset}
        />
        <div className="map-hint glass">{depot ? 'Клик по карте — добавить точку' : 'Клик по карте — поставить склад'}</div>
      </main>
    </div>
  )
}
