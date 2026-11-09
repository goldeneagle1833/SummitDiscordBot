import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  loadLocalSeen, mergeSeen, newPageKeys, pageKeyForPath, saveLocalSeen,
} from '@/utils/newContent'

const REFRESH_MS = 15 * 60 * 1000

// Which menu pages have content this person hasn't seen yet. Opening a page
// clears its dot.
export default function useNewContent(user, pathname) {
  const [latest, setLatest] = useState({})
  const [seen, setSeen] = useState(() => loadLocalSeen())
  const userId = user?.user_id || null
  const userRef = useRef(userId)
  userRef.current = userId

  const load = useCallback(() => {
    fetch('/api/nav/new-content', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return
        setLatest(data.latest || {})
        if (data.seen) {
          setSeen((prev) => {
            const merged = mergeSeen(prev, data.seen)
            saveLocalSeen(merged)
            return merged
          })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [load, userId])

  const newKeys = useMemo(() => newPageKeys(latest, seen), [latest, seen])

  // Opening a page with a dot marks it seen
  const pageKey = pageKeyForPath(pathname)
  useEffect(() => {
    if (!pageKey || !newKeys.has(pageKey)) return
    // Mark with the content's own time so a slow device clock can't bring the dot back
    const stamp = latest[pageKey]
    setSeen((prev) => {
      const next = mergeSeen(prev, { [pageKey]: stamp })
      saveLocalSeen(next)
      return next
    })
    if (userRef.current) {
      fetch('/api/nav/seen', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pages: [pageKey] }),
      }).catch(() => {})
    }
  }, [pageKey, newKeys, latest])

  return newKeys
}
