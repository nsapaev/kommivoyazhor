import { useState, type FormEvent } from 'react'
import type { Place } from '../types.ts'

interface Props {
  stop: Place
  onSave: (stop: Place) => void
  onCancel: () => void
}

/** Подробности точки: подпись, телефон, окно доставки, комментарий для водителя. */
export default function StopEditor({ stop, onSave, onCancel }: Props) {
  const [label, setLabel] = useState(stop.label)
  const [phone, setPhone] = useState(stop.phone ?? '')
  const [from, setFrom] = useState(stop.tw_from ?? '')
  const [to, setTo] = useState(stop.tw_to ?? '')
  const [comment, setComment] = useState(stop.comment ?? '')

  const bad = !!(from && to && from > to)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (bad) return
    onSave({
      ...stop,
      label: label.trim() || stop.label,
      phone: phone.trim(),
      comment: comment.trim(),
      tw_from: from || null,
      tw_to: to || null,
    })
  }

  return (
    <form className="stop-editor" onSubmit={submit}>
      <label className="input">
        <span>Название</span>
        <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={300} autoFocus />
      </label>
      <label className="input">
        <span>Телефон клиента</span>
        <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} placeholder="+998 90 123 45 67" />
      </label>
      <div className="input">
        <span>Привезти</span>
        <div className="stop-editor__window">
          <label>
            с <input type="time" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>
            до <input type="time" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          {(from || to) && (
            <button type="button" className="link" onClick={() => (setFrom(''), setTo(''))}>
              Любое время
            </button>
          )}
        </div>
        {bad && <span className="hint hint--warn">«С» позже, чем «до»</span>}
      </div>
      <label className="input">
        <span>Комментарий для водителя</span>
        <input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={300} placeholder="Подъезд 3, домофон 45" />
      </label>
      <div className="row">
        <button className="btn btn--primary" disabled={bad}>
          Готово
        </button>
        <button type="button" className="btn btn--ghost" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </form>
  )
}
