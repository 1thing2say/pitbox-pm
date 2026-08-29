import { useCallback, useEffect, useRef, useState } from 'react'

export interface ToastState {
  message: string
  isError: boolean
}

export function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const clear = useCallback(() => {
    if (timer.current !== undefined) window.clearTimeout(timer.current)
  }, [])

  const show = useCallback(
    (message: string, isError = false) => {
      clear()
      setToast({ message, isError })
      timer.current = window.setTimeout(() => setToast(null), isError ? 6000 : 2600)
    },
    [clear],
  )

  const showError = useCallback(
    (err: unknown) => {
      show(err instanceof Error ? err.message : String(err), true)
    },
    [show],
  )

  // Don't leave a timer running against an unmounted component.
  useEffect(() => clear, [clear])

  return { toast, show, showError }
}
