import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

// Состояние, которое переживает перезагрузку страницы.
export function usePersistentState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = localStorage.getItem(key)
      return saved !== null ? (JSON.parse(saved) as T) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* хранилище недоступно — просто не запоминаем */
    }
  }, [key, value])

  return [value, setValue]
}
