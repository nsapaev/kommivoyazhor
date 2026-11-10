import { useRef, useState, type ChangeEvent } from 'react'
import { geocode, importPoints } from '../api.ts'
import type { ImportRow, Place } from '../types.ts'

interface Props {
  onAdd: (places: Place[]) => void
  onClose: () => void
}

const HEADER = ['Адрес', 'Клиент', 'Телефон', 'С', 'До', 'Комментарий']

const toPlace = (r: ImportRow, lat: number, lon: number): Place => ({
  lat,
  lon,
  label: [r.name, r.address].filter(Boolean).join(' — ') || `Точка ${lat.toFixed(5)}, ${lon.toFixed(5)}`,
  phone: r.phone,
  comment: r.comment,
  tw_from: r.tw_from,
  tw_to: r.tw_to,
})

/** Ненайденные строки возвращаем в поле. Если у них были телефон или время — таблицей, чтобы не потерять. */
const backToText = (rows: ImportRow[]) =>
  rows.some((r) => r.name || r.phone || r.comment || r.tw_from || r.tw_to)
    ? [HEADER, ...rows.map((r) => [r.address, r.name, r.phone, r.tw_from ?? '', r.tw_to ?? '', r.comment])]
        .map((cols) => cols.join('\t'))
        .join('\n')
    : rows.map((r) => r.address).join('\n')

// Список адресов: вставить текстом (можно прямо из Excel) или загрузить файл .xlsx / .csv.
export default function BulkImport({ onAdd, onClose }: Props) {
  const [text, setText] = useState('')
  const [progress, setProgress] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'warn' | 'error'; text: string } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const run = async (body: Blob | string, kind: 'file' | 'text') => {
    setMessage(null)
    setProgress('Читаю…')
    try {
      const { rows, skipped, truncated } = await importPoints(body, kind)
      const found: Place[] = []
      const missed: ImportRow[] = []
      for (let i = 0; i < rows.length; i++) {
        const r = rows[i]
        if (r.lat !== null && r.lon !== null) {
          found.push(toPlace(r, r.lat, r.lon))
          continue
        }
        setProgress(`Ищу адреса: ${i + 1} из ${rows.length}`)
        try {
          const [first] = await geocode(r.address)
          if (first) found.push(toPlace(r, first.lat, first.lon))
          else missed.push(r)
        } catch {
          missed.push(r)
        }
      }
      if (found.length) onAdd(found)

      const notes = [
        missed.length && `Не нашлись ${missed.length} адр. — они остались в поле: поправьте и нажмите «Добавить» ещё раз.`,
        skipped && `Пропущено строк без адреса: ${skipped}.`,
        truncated && 'В файле больше 100 строк — взяты первые 100.',
      ].filter(Boolean)
      setText(backToText(missed))
      if (notes.length) setMessage({ kind: 'warn', text: notes.join(' ') })
      else onClose()
    } catch (e) {
      setMessage({ kind: 'error', text: (e as Error).message })
    } finally {
      setProgress(null)
    }
  }

  const onFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // чтобы тот же файл можно было выбрать снова
    if (file) run(file, 'file')
  }

  return (
    <div className="bulk">
      <textarea
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          'Каждый адрес с новой строки — или вставьте столбцы прямо из Excel\n' +
          'Ташкент, улица Амира Темура 1\n' +
          'Ташкент, Чиланзар, улица Бунёдкор 15'
        }
        disabled={!!progress}
      />
      {message && <p className={message.kind === 'error' ? 'notice notice--error' : 'hint hint--warn'}>{message.text}</p>}
      <div className="row">
        <button className="btn" onClick={() => run(text, 'text')} disabled={!text.trim() || !!progress}>
          {progress ?? 'Добавить'}
        </button>
        <button className="btn btn--ghost" onClick={() => fileRef.current?.click()} disabled={!!progress}>
          Загрузить Excel / CSV
        </button>
        <button className="btn btn--ghost" onClick={onClose} disabled={!!progress}>
          Отмена
        </button>
      </div>
      <input
        ref={fileRef}
        type="file"
        accept=".xlsx,.csv,.txt,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
        onChange={onFile}
        hidden
      />
      <p className="hint">
        В файле нужна колонка «Адрес». Ещё можно: «Клиент», «Телефон», «С» и «До» (окно доставки), «Комментарий».{' '}
        <a className="link" href="/api/import/template.csv" download>
          Скачать образец
        </a>
      </p>
    </div>
  )
}
