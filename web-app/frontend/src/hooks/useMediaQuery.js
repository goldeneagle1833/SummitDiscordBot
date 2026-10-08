import { useEffect, useState } from 'react'

function matches(query) {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(query).matches
    : false
}

/** True while the CSS media query matches; updates live on resize/rotation. */
export default function useMediaQuery(query) {
  const [value, setValue] = useState(() => matches(query))

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const mql = window.matchMedia(query)
    const onChange = (e) => setValue(e.matches)
    setValue(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [query])

  return value
}

/** Tailwind's `lg` breakpoint — where the event list stops being an accordion. */
export const useIsDesktop = () => useMediaQuery('(min-width: 1024px)')

/** Honour the user's reduced-motion setting when scrolling programmatically. */
export const usePrefersReducedMotion = () => useMediaQuery('(prefers-reduced-motion: reduce)')
