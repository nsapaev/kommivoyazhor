import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react'

const MOBILE_QUERY = '(max-width: 760px)'
const PEEK_PX = 170 // видны компания и шапка маршрутного листа

/** Узкий экран — телефон. */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY)
    const on = () => setMobile(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return mobile
}

export type SheetSnap = 0 | 1 | 2 // шапка · половина · почти весь экран

/**
 * Выдвижная шторка снизу: тянется пальцем за «язычок» и встаёт в одно из трёх положений,
 * короткое нажатие переключает положения по кругу.
 */
export function useBottomSheet(enabled: boolean) {
  const [vh, setVh] = useState(() => window.innerHeight)
  const [snap, setSnap] = useState<SheetSnap>(1)
  const [dragVisible, setDragVisible] = useState<number | null>(null)
  const start = useRef<{ y: number; visible: number; moved: boolean } | null>(null)

  useEffect(() => {
    const on = () => setVh(window.innerHeight)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])

  const maxH = Math.round(vh * 0.9)
  const snaps = [PEEK_PX, Math.round(vh * 0.5), maxH]
  const visible = dragVisible ?? snaps[snap]

  const onPointerDown = (e: PointerEvent<HTMLElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    start.current = { y: e.clientY, visible, moved: false }
  }
  const onPointerMove = (e: PointerEvent<HTMLElement>) => {
    const s = start.current
    if (!s) return
    const dy = s.y - e.clientY
    if (Math.abs(dy) > 6) s.moved = true
    if (s.moved) setDragVisible(Math.min(maxH, Math.max(PEEK_PX - 40, s.visible + dy)))
  }
  const onPointerUp = () => {
    const s = start.current
    start.current = null
    if (!s) return
    if (!s.moved) {
      setSnap((v) => ((v + 1) % 3) as SheetSnap)
    } else if (dragVisible !== null) {
      // ближайшее положение
      const nearest = snaps.reduce((best, h, i) => (Math.abs(h - dragVisible) < Math.abs(snaps[best] - dragVisible) ? i : best), 0)
      setSnap(nearest as SheetSnap)
    }
    setDragVisible(null)
  }

  const style: CSSProperties | undefined = enabled
    ? {
        height: maxH,
        transform: `translateY(${maxH - visible}px)`,
        // Шторка сдвинута вниз на эту величину: столько же отступа внизу прокрутки,
        // иначе конец списка (машины, кнопка «Построить») окажется за краем экрана.
        ['--sheet-hidden' as string]: `${maxH - visible}px`,
        transition: dragVisible === null ? 'transform 0.38s cubic-bezier(0.2, 0.8, 0.2, 1)' : 'none',
      }
    : undefined

  return {
    style,
    /** Сколько пикселей карты закрыто шторкой — чтобы точки не прятались под неё. */
    inset: enabled ? snaps[snap] : 0,
    snap,
    setSnap,
    handleProps: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: onPointerUp },
  }
}
