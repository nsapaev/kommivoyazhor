import { Fragment, useEffect } from 'react'
import L, { type LatLng, type LatLngTuple } from 'leaflet'
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { DEPOT_COLOR, PENDING_COLOR, vehicleColor } from '../colors.ts'
import type { MapStyle, Place, Route } from '../types.ts'

const DEFAULT_CENTER: LatLngTuple = [41.3111, 69.2797] // Ташкент

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const ESRI_ATTR = 'Снимки &copy; Esri, Maxar, Earthstar Geographics'

const pin = (text: string | number, color: string, isDepot = false) =>
  L.divIcon({
    className: '',
    html: `<div class="pin${isDepot ? ' pin--depot' : ''}" style="background:${color}">${text}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })

function ClickHandler({ onClick }: { onClick: (latlng: LatLng) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng) })
  return null
}

function FitBounds({ points, bottomInset }: { points: LatLngTuple[]; bottomInset: number }) {
  const map = useMap()
  const key = points.map((p) => p.join()).join(';')
  useEffect(() => {
    // Без анимации: Leaflet пропускает новый fitBounds, пока идёт анимация прошлого,
    // а склад и точки приходят с сервера друг за другом.
    if (points.length === 1) map.setView(points[0], 14, { animate: false })
    if (points.length > 1)
      map.fitBounds(points, { paddingTopLeft: [40, 70], paddingBottomRight: [40, 40 + bottomInset], animate: false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return null
}

function BaseLayer({ style }: { style: MapStyle }) {
  if (style === 'hybrid') {
    return (
      <>
        <TileLayer key="sat" attribution={ESRI_ATTR} url={`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`} maxNativeZoom={19} />
        <TileLayer key="roads" url={`${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`} opacity={0.55} />
        <TileLayer key="labels" url={`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`} />
      </>
    )
  }
  // OpenStreetMap — самые подробные данные по Узбекистану (улицы, дома, махалли).
  // Цвет убираем в CSS: остаётся спокойная тёплая монохромная карта, цветные — только маршруты.
  return (
    <TileLayer
      key="osm"
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      maxZoom={19}
    />
  )
}

const STYLE_LABELS: Record<MapStyle, string> = { scheme: 'Схема', hybrid: 'Гибрид' }

interface Props {
  depot: Place | null
  stops: Place[]
  routes?: Route[]
  mapStyle: MapStyle
  onMapStyleChange: (style: MapStyle) => void
  onMapClick: (latlng: LatLng) => void
  /** Высота шторки снизу (телефон), чтобы точки не прятались под неё. */
  bottomInset?: number
}

export default function MapView({ depot, stops, routes, mapStyle, onMapStyleChange, onMapClick, bottomInset = 0 }: Props) {
  const all: LatLngTuple[] = [depot, ...stops].filter((p): p is Place => !!p).map((p) => [p.lat, p.lon])

  // Номер точки в маршруте её машины — для подписи на карте.
  const routeOf = new Map<string, { vehicle: number; n: number }>()
  routes?.forEach((r) => r.stops.forEach((s, i) => routeOf.set(`${s.lat},${s.lon}`, { vehicle: r.vehicle, n: i + 1 })))

  return (
    <div className={`map-shell map-shell--${mapStyle}`}>
      <MapContainer center={DEFAULT_CENTER} zoom={12} className="map">
        <BaseLayer style={mapStyle} />
        <ClickHandler onClick={onMapClick} />
        <FitBounds points={all} bottomInset={bottomInset} />

        {depot &&
          routes?.map((r) => {
            const line = r.geometry ?? [[depot.lat, depot.lon], ...r.stops.map((s): LatLngTuple => [s.lat, s.lon])]
            const dash = r.geometry ? undefined : '6 8'
            return (
              <Fragment key={r.vehicle}>
                {/* белая обводка — линия читается и на схеме, и на спутнике */}
                <Polyline positions={line} pathOptions={{ color: '#fff', weight: 9, opacity: 0.9, dashArray: dash }} />
                <Polyline positions={line} pathOptions={{ color: vehicleColor(r.vehicle), weight: 5, opacity: 1, dashArray: dash }} />
              </Fragment>
            )
          })}

        {stops.map((s, i) => {
          const info = routeOf.get(`${s.lat},${s.lon}`)
          return (
            <Marker
              key={`${s.lat},${s.lon},${i}`}
              position={[s.lat, s.lon]}
              icon={info ? pin(info.n, vehicleColor(info.vehicle)) : pin(i + 1, PENDING_COLOR)}
            >
              <Tooltip>{s.label}</Tooltip>
            </Marker>
          )
        })}

        {depot && (
          <Marker position={[depot.lat, depot.lon]} icon={pin('С', DEPOT_COLOR, true)}>
            <Tooltip>Склад: {depot.label}</Tooltip>
          </Marker>
        )}
      </MapContainer>

      <div className="segmented map-style">
        {(Object.keys(STYLE_LABELS) as MapStyle[]).map((s) => (
          <button key={s} className={s === mapStyle ? 'active' : ''} onClick={() => onMapStyleChange(s)}>
            {STYLE_LABELS[s]}
          </button>
        ))}
      </div>
    </div>
  )
}
