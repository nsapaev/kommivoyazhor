import { useState, type CSSProperties } from 'react'
import { vehicleColor } from '../colors.ts'
import { planTitle } from '../dates.ts'
import { driverUrl, isLate, stopKey, windowText } from '../stops.ts'
import type { Route, StopStatus } from '../types.ts'

const formatTime = (min: number) => (min < 60 ? `${min} мин` : `${Math.floor(min / 60)} ч ${min % 60} мин`)

interface Props {
  route: Route
  planDate: string
  statuses: Record<string, StopStatus>
  startTime?: string
}

export default function RouteCard({ route, planDate, statuses, startTime }: Props) {
  const [copied, setCopied] = useState(false)

  // В старых расчётах частей нет — тогда одна ссылка.
  const parts = route.parts?.length ? route.parts : [{ title: 'Весь маршрут', link: route.link }]
  const split = parts.length > 1
  const etas = route.etas ?? []

  const status = route.stops.map((s) => statuses[stopKey(s)])
  const done = status.filter((x) => x === 'done').length
  const failed = status.filter((x) => x === 'failed').length
  const late = route.stops.filter((s, i) => isLate(s, etas[i])).length

  // Водителю отправляем его страницу; в старых расчётах её нет — тогда ссылки Яндекса.
  const link = route.driver_token
    ? driverUrl(route.driver_token)
    : split
      ? parts.map((p) => `${p.title}\n${p.link}`).join('\n\n')
      : parts[0].link
  const title = `Маршрут на ${planTitle(planDate).toLowerCase()}, машина ${route.vehicle}`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      window.prompt('Скопируйте', link)
    }
  }

  const share = route.driver_token
    ? `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(title)}`
    : `https://t.me/share/url?url=${encodeURIComponent(parts[0].link)}&text=${encodeURIComponent(split ? link : title)}`

  const yandexButtons = split ? (
    <div className="parts">
      <p className="hint">
        Яндекс Карты прокладывают не больше 20 точек за раз, поэтому маршрут разбит на {parts.length} части.
      </p>
      {parts.map((p, i) => (
        <a key={i} className="btn parts__btn" href={p.link} target="_blank" rel="noreferrer">
          {p.title}
        </a>
      ))}
    </div>
  ) : (
    <a className="btn parts__btn" href={parts[0].link} target="_blank" rel="noreferrer">
      Открыть в Яндекс Картах
    </a>
  )

  return (
    <div className="card" style={{ '--c': vehicleColor(route.vehicle) } as CSSProperties}>
      <div className="card__head">
        <span className="dot" />
        <strong>Машина {route.vehicle}</strong>
        <span className="muted">
          {route.stops.length} точ. · {route.distance_km} км ·{' '}
          {startTime && route.finish ? `${startTime}–${route.finish}` : formatTime(route.duration_min)}
        </span>
      </div>

      {(done > 0 || failed > 0) && (
        <p className="card__progress">
          Доставлено <strong>{done}</strong> из {route.stops.length}
          {failed > 0 && <span className="card__failed"> · не получилось {failed}</span>}
        </p>
      )}

      <ol className="card__stops">
        {route.stops.map((s, i) => {
          const win = windowText(s)
          const isLateStop = isLate(s, etas[i])
          return (
            <li key={i} className={status[i] ? `is-${status[i]}` : undefined}>
              <span className="card__stop-label">
                {status[i] === 'done' && <span className="mark mark--done" title="Доставлено">✓</span>}
                {status[i] === 'failed' && <span className="mark mark--failed" title="Не получилось">!</span>}
                {s.label}
              </span>
              <span className="card__stop-time">
                {win && <span className={`tw${isLateStop ? ' tw--late' : ''}`}>{win}</span>}
                {etas[i] && <span className="muted">≈ {etas[i]}</span>}
              </span>
            </li>
          )
        })}
      </ol>

      {late > 0 && (
        <p className="notice">
          {late} {late === 1 ? 'точка' : 'точки'} не успевает ко времени — добавьте машину или начните смену раньше.
        </p>
      )}

      {route.driver_token ? (
        <>
          <div className="row">
            <a className="btn btn--primary" href={share} target="_blank" rel="noreferrer">
              Отправить водителю в Telegram
            </a>
            <button className="btn btn--ghost" onClick={copy}>
              {copied ? 'Скопировано' : 'Копировать ссылку'}
            </button>
            <a className="btn btn--ghost" href={link} target="_blank" rel="noreferrer">
              Открыть
            </a>
          </div>
          <p className="hint">
            По ссылке водитель видит точки по порядку, звонит клиенту, открывает навигатор и отмечает «Доставлено».
          </p>
          <details className="card__yandex">
            <summary>Весь маршрут в Яндекс Картах</summary>
            {yandexButtons}
          </details>
        </>
      ) : (
        <>
          {yandexButtons}
          <div className="row">
            <button className="btn btn--ghost" onClick={copy}>
              {copied ? 'Скопировано' : split ? 'Копировать все ссылки' : 'Копировать ссылку'}
            </button>
            <a className="btn btn--ghost" href={share} target="_blank" rel="noreferrer">
              В Telegram
            </a>
          </div>
          <p className="hint">Нажмите «Пересчитать» — появится страница для водителя с отметками.</p>
        </>
      )}
    </div>
  )
}
