import { useEffect, useState } from 'react'

function getDesktopPreference() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(hover: hover) and (pointer: fine)').matches
}

export default function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(getDesktopPreference)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined
    const mq = window.matchMedia('(hover: hover) and (pointer: fine)')
    const listener = (event) => setIsDesktop(event.matches)
    if (mq.addEventListener) {
      mq.addEventListener('change', listener)
      return () => mq.removeEventListener('change', listener)
    }
    mq.addListener(listener)
    return () => mq.removeListener(listener)
  }, [])

  return isDesktop
}
