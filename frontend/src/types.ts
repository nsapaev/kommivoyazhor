export interface Place {
  lat: number
  lon: number
  label: string
  phone?: string
  comment?: string
  /** Окно доставки «с» / «до», ЧЧ:ММ */
  tw_from?: string | null
  tw_to?: string | null
}

export interface Route {
  vehicle: number
  stops: Place[]
  distance_km: number
  duration_min: number
  link: string
  /** Ссылки по частям: Яндекс Карты прокладывают не больше 20 точек за раз. */
  parts?: { title: string; link: string }[]
  /** Линия по дорогам [[lat, lon], …]; null — если OSRM не отдал геометрию. */
  geometry: [number, number][] | null
  /** Прибытие на каждую точку, ЧЧ:ММ */
  etas?: string[]
  /** Когда машина закончит, ЧЧ:ММ */
  finish?: string | null
  /** Секретная ссылка водителя: /d/<token> */
  driver_token?: string | null
}

export interface BuildResult {
  /** Склад на момент расчёта. */
  depot: Place
  routes: Route[]
  /** true — OSRM недоступен, расчёт по прямой. */
  approximate: boolean
  start_time?: string
}

export interface Settings {
  depot: Place | null
  vehicles: number
  service_min: number
  return_to_depot: boolean
  start_time: string
}

export interface PlanSummary {
  id: number
  /** YYYY-MM-DD */
  plan_date: string
  status: 'draft' | 'built'
  stops_count: number
  routes_count: number
  total_km: number
  updated_at: string
}

export interface Plan extends PlanSummary {
  stops: Place[]
  vehicles: number
  service_min: number
  return_to_depot: boolean
  start_time: string
  result: BuildResult | null
  /** Отметки водителей: «lat,lon» точки → статус */
  statuses: Record<string, StopStatus>
}

export type StopStatus = 'done' | 'failed'

export type PlanPatch = Partial<Pick<Plan, 'stops' | 'vehicles' | 'service_min' | 'return_to_depot' | 'start_time'>>

export type MapStyle = 'scheme' | 'hybrid'

export interface Me {
  user_id: number
  name: string
  email: string
  role: string
  company_id: number
  company_name: string
}

export interface RegisterRequest {
  company: string
  name: string
  email: string
  password: string
}

export interface DriverStop extends Place {
  eta: string | null
  status: StopStatus | null
}

export interface DriverView {
  company: string
  plan_date: string
  vehicle: number
  /** false — маршрут сейчас меняют */
  ready: boolean
  /** Маршрут построен, но этой машине точек не досталось */
  empty?: boolean
  depot: Place | null
  return_to_depot: boolean
  start_time: string | null
  finish: string | null
  stops: DriverStop[]
}

export interface ImportRow {
  address: string
  name: string
  phone: string
  comment: string
  tw_from: string | null
  tw_to: string | null
  lat: number | null
  lon: number | null
}

export interface ImportResult {
  rows: ImportRow[]
  skipped: number
  truncated: boolean
}
