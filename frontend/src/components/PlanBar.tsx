import { useState } from 'react'
import { planTitle, shortDate } from '../dates.ts'
import type { PlanSummary } from '../types.ts'

interface Props {
  current: PlanSummary
  plans: PlanSummary[]
  onOpen: (id: number) => void
  onNew: () => void
  onRepeat: (id: number) => void
  onDelete: (id: number) => void
}

const RELATIVE = ['Сегодня', 'Вчера', 'Завтра']

const meta = (p: PlanSummary) =>
  p.status === 'built'
    ? `${p.stops_count} точ. · ${p.routes_count} маш. · ${p.total_km} км`
    : p.stops_count
      ? `черновик · ${p.stops_count} точ.`
      : 'черновик · пусто'

// Шапка текущего маршрутного листа и история прошлых дней.
export default function PlanBar({ current, plans, onOpen, onNew, onRepeat, onDelete }: Props) {
  const [open, setOpen] = useState(false)
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const title = planTitle(current.plan_date)

  return (
    <section className="plan">
      <div className="plan__head">
        <div className="plan__title">
          <strong>{title}</strong>
          <span className="muted">
            {RELATIVE.includes(title) ? `${shortDate(current.plan_date)} · ` : ''}
            {current.status === 'built' ? 'маршрут построен' : 'черновик'}
          </span>
        </div>
        <button className={`btn btn--ghost btn--sm${open ? ' is-on' : ''}`} onClick={() => setOpen((v) => !v)}>
          История{plans.length > 1 ? ` · ${plans.length}` : ''}
        </button>
        <button className="btn btn--sm" onClick={onNew} title="Новый маршрутный лист на сегодня">
          + Новый
        </button>
      </div>

      {open && (
        <ul className="history">
          {plans.map((p) => (
            <li key={p.id} className={p.id === current.id ? 'is-current' : ''}>
              <button className="history__main" onClick={() => onOpen(p.id)}>
                <span className={`badge badge--${p.status}`} />
                <span className="history__text">
                  <strong>{planTitle(p.plan_date)}</strong>
                  <span className="muted">{meta(p)}</span>
                </span>
              </button>
              {p.stops_count > 0 && (
                <button className="link" onClick={() => onRepeat(p.id)} title="Те же точки в новый лист на сегодня">
                  Повторить
                </button>
              )}
              {confirmId === p.id ? (
                <button
                  className="link link--danger"
                  onClick={() => {
                    setConfirmId(null)
                    onDelete(p.id)
                  }}
                  onBlur={() => setConfirmId(null)}
                  autoFocus
                >
                  Удалить?
                </button>
              ) : (
                <button className="icon-btn" title="Удалить" onClick={() => setConfirmId(p.id)}>
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
