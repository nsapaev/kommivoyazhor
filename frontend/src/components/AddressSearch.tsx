import { useEffect, useRef, useState } from 'react'
import { geocode } from '../api.ts'
import type { Place } from '../types.ts'

interface Props {
  placeholder: string
  onPick: (place: Place) => void
}

// Поле адреса с подсказками.
export default function AddressSearch({ placeholder, onPick }: Props) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<Place[]>([])
  const [status, setStatus] = useState('')
  const reqId = useRef(0)

  useEffect(() => {
    const q = query.trim()
    if (q.length < 3) {
      setOptions([])
      setStatus('')
      return
    }
    const id = ++reqId.current
    const timer = setTimeout(async () => {
      setStatus('Ищу…')
      try {
        const found = await geocode(q)
        if (id !== reqId.current) return
        setOptions(found)
        setStatus(found.length ? '' : 'Ничего не нашлось — уточните адрес или поставьте точку на карте')
      } catch (e) {
        if (id === reqId.current) setStatus((e as Error).message)
      }
    }, 600)
    return () => clearTimeout(timer)
  }, [query])

  const pick = (o: Place) => {
    onPick({ label: shortLabel(o.label), lat: o.lat, lon: o.lon })
    reqId.current++
    setQuery('')
    setOptions([])
    setStatus('')
  }

  return (
    <div className="search">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && options[0] && pick(options[0])}
        placeholder={placeholder}
      />
      {options.length > 0 && (
        <ul className="search__list">
          {options.map((o, i) => (
            <li key={i}>
              <button type="button" onClick={() => pick(o)}>
                {o.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {status && <p className="hint">{status}</p>}
    </div>
  )
}

// «дом, улица, район» вместо длинной строки Nominatim.
export function shortLabel(label: string): string {
  return label.split(', ').slice(0, 3).join(', ')
}
