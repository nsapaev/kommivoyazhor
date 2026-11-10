import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { getDriverRoute, setDriverStatus } from '../api.ts'
import { vehicleColor } from '../colors.ts'
import { planTitle } from '../dates.ts'
import { isLate, windowText, yandexFromHere } from '../stops.ts'
import type { DriverStop, DriverView, StopStatus } from '../types.ts'

/** Сколько точек за раз отдаём в Яндекс Карты (их лимит — 20, первая — «от меня»). */
const NAV_BATCH = 19

export default function DriverPage({ token }: { token: string }) {
  const [view, setView] = useState<DriverView | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setView(await getDriverRoute(token))
      setError('')
    } catch (e) {
      setError((e as Error).message)
    }
  }, [token])

  // Загрузка и обновление, когда водитель возвращается в браузер из навигатора.
  useEffect(() => {
    load()
    const onVisible = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [load])

  const mark = async (index: number, status: StopStatus | null) => {
    if (!view) return
    const before = view
    setView({ ...view, stops: view.stops.map((s, i) => (i === index ? { ...s, status } : s)) })
    setBusy(index)
    try {
      setView(await setDriverStatus(token, index, status))
      setError('')
    } catch (e) {
      setView(before)
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (!view) {
    return (
      <div className="driver">
        {error ? (
          <div className="driver__card glass">
            <p className="notice notice--error">{error}</p>
            <button className="btn btn--wide" onClick={load}>
              Попробовать ещё раз
            </button>
          </div>
        ) : (
          <p className="hint driver__loading">Загружаю маршрут…</p>
        )}
      </div>
    )
  }

  const color = vehicleColor(view.vehicle)
  const header = (
    <header className="driver__head">
      <span className="muted">{view.company}</span>
      <h1>
        <span className="dot" style={{ '--c': color } as CSSProperties} /> Машина {view.vehicle}
      </h1>
      <span className="muted">
        {planTitle(view.plan_date)}
        {view.ready && view.start_time && view.finish && ` · ${view.start_time} – ${view.finish}`}
      </span>
    </header>
  )

  if (!view.ready) {
    return (
      <div className="driver">
        <div className="driver__card glass">
          {header}
          <p className="notice">
            {view.empty
              ? 'В этом маршрутном листе для вашей машины точек нет. Если это ошибка — спросите диспетчера.'
              : 'Диспетчер сейчас меняет маршрут. Обновите страницу через минуту.'}
          </p>
          <button className="btn btn--primary btn--wide" onClick={load}>
            Обновить
          </button>
        </div>
      </div>
    )
  }

  const total = view.stops.length
  const done = view.stops.filter((s) => s.status === 'done').length
  const failed = view.stops.filter((s) => s.status === 'failed').length
  const pending = view.stops.map((s, i) => ({ s, i })).filter(({ s }) => !s.status)
  const nextIndex = pending[0]?.i ?? -1

  // Маршрут по оставшимся точкам; склад в конце — если машина возвращается и всё влезает.
  const navPoints: DriverStop[] = pending.slice(0, NAV_BATCH).map(({ s }) => s)
  const backToDepot = view.return_to_depot && view.depot && pending.length < NAV_BATCH
  const navLink = navPoints.length
    ? yandexFromHere(backToDepot ? [...navPoints, { ...view.depot!, eta: null, status: null }] : navPoints)
    : view.depot && view.return_to_depot
      ? yandexFromHere([view.depot])
      : null

  return (
    <div className="driver">
      <div className="driver__card glass">
        {header}

        <div className="driver__progress" aria-label={`Отмечено ${done + failed} из ${total}`}>
          <div className="driver__bar">
            <i className="is-done" style={{ width: `${(done / total) * 100}%` }} />
            <i className="is-failed" style={{ width: `${(failed / total) * 100}%` }} />
          </div>
          <span>
            Доставлено <strong>{done}</strong> из {total}
            {failed > 0 && <span className="driver__failed"> · не получилось {failed}</span>}
          </span>
        </div>

        {navLink && (
          <a className="btn btn--primary btn--big btn--wide" href={navLink} target="_blank" rel="noreferrer">
            {pending.length === 0
              ? 'Маршрут обратно на склад'
              : pending.length > NAV_BATCH
                ? `Поехали: следующие ${NAV_BATCH} точек`
                : 'Поехали по оставшимся точкам'}
          </a>
        )}
        {pending.length === 0 && <p className="notice notice--ok">Все точки отмечены. Спасибо!</p>}
        {error && <p className="notice notice--error">{error}</p>}
      </div>

      <ol className="driver__stops">
        {view.stops.map((s, i) => {
          const late = isLate(s, s.eta)
          const win = windowText(s)
          return (
            <li
              key={i}
              className={`driver__stop glass${s.status ? ` is-${s.status}` : ''}${i === nextIndex ? ' is-next' : ''}`}
            >
              <div className="driver__stop-head">
                <span className="driver__num" style={{ '--c': color } as CSSProperties}>
                  {s.status === 'done' ? '✓' : s.status === 'failed' ? '!' : i + 1}
                </span>
                <div className="driver__stop-text">
                  <strong>{s.label}</strong>
                  <span className="muted">
                    {s.eta && `≈ ${s.eta}`}
                    {win && (
                      <span className={`tw${late ? ' tw--late' : ''}`} title={late ? 'Не успевает к этому времени' : undefined}>
                        {win}
                      </span>
                    )}
                  </span>
                </div>
              </div>

              {s.comment && <p className="driver__comment">{s.comment}</p>}

              {s.status ? (
                <div className="driver__status">
                  <span>{s.status === 'done' ? 'Доставлено' : 'Не получилось'}</span>
                  <button className="link" onClick={() => mark(i, null)} disabled={busy === i}>
                    Отменить
                  </button>
                </div>
              ) : (
                <div className="driver__actions">
                  <a className={`btn btn--ghost${s.phone ? '' : ' is-wide'}`} href={yandexFromHere([s])} target="_blank" rel="noreferrer">
                    Навигатор
                  </a>
                  {s.phone && (
                    <a className="btn btn--ghost" href={`tel:${s.phone.replace(/[^\d+]/g, '')}`}>
                      Позвонить
                    </a>
                  )}
                  <button className="btn btn--primary" onClick={() => mark(i, 'done')} disabled={busy === i}>
                    Доставлено
                  </button>
                  <button className="btn btn--ghost" onClick={() => mark(i, 'failed')} disabled={busy === i}>
                    Не получилось
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ol>

      <button className="link driver__refresh" onClick={load}>
        Обновить маршрут
      </button>
    </div>
  )
}
