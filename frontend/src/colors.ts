// Цвета машин под палитру myJamo: коралловый акцент, сирень-синий, янтарный, зелёный, фиолетовый.
export const VEHICLE_COLORS = ['#ff6b57', '#5b74f0', '#f0a030', '#1fb26a', '#a070e8'] as const

export const DEPOT_COLOR = '#23262b'
export const PENDING_COLOR = '#9a9690'

export const vehicleColor = (n: number): string => VEHICLE_COLORS[(n - 1) % VEHICLE_COLORS.length]
