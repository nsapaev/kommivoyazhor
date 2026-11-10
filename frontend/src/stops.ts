import type { Place } from './types.ts'

/** Ключ точки для отметок водителя — как на сервере: координаты с 6 знаками. */
export const stopKey = (p: Place) => `${p.lat.toFixed(6)},${p.lon.toFixed(6)}`

/** «10:00–12:00», «с 10:00», «до 14:00» или пусто. */
export const windowText = (p: Place) =>
  p.tw_from && p.tw_to ? `${p.tw_from}–${p.tw_to}` : p.tw_from ? `с ${p.tw_from}` : p.tw_to ? `до ${p.tw_to}` : ''

/** Приедет позже окна. Время в ЧЧ:ММ сравнивается как строка. */
export const isLate = (p: Place, eta?: string | null) => !!(eta && p.tw_to && eta > p.tw_to)

const coords = (p: Place) => `${p.lat.toFixed(6)},${p.lon.toFixed(6)}`

/** Яндекс Карты: от текущего местоположения через точки (пустая первая точка — «от меня»). */
export const yandexFromHere = (points: Place[]) =>
  `https://yandex.ru/maps/?rtext=~${points.map(coords).join('~')}&rtt=auto`

export const driverUrl = (token: string) => `${window.location.origin}/d/${token}`
