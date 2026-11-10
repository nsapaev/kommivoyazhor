/** Сегодняшняя дата по часам пользователя: YYYY-MM-DD. */
export function todayISO(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const shift = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** «Сегодня», «Вчера», «Завтра» или «Вторник, 11 ноября». */
export function planTitle(iso: string): string {
  const today = todayISO()
  if (iso === today) return 'Сегодня'
  if (iso === shift(today, -1)) return 'Вчера'
  if (iso === shift(today, 1)) return 'Завтра'
  const text = new Date(`${iso}T12:00:00`).toLocaleDateString('ru-RU', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    ...(iso.slice(0, 4) !== today.slice(0, 4) ? { year: 'numeric' } : {}),
  })
  return text[0].toUpperCase() + text.slice(1)
}

/** «11 ноября» — подпись под «Сегодня». */
export const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
