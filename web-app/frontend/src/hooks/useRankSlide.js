import { useLayoutEffect, useRef } from 'react'

/**
 * Glide re-sorted rows to their new place instead of jumping (FLIP).
 *
 * Attach the returned ref to a list whose direct children carry
 * `data-rank-key`. When a row's position changes between renders, it starts
 * where it was and slides into place; rows new to the list fade in. Timing
 * follows the --bar-ms / --bar-ease variables shared with the bar widths.
 */
export default function useRankSlide() {
  const ref = useRef(null)
  const prev = useRef(null)

  useLayoutEffect(() => {
    const list = ref.current
    if (!list) {
      prev.current = null
      return
    }
    const next = new Map()
    const moved = []
    for (const row of list.children) {
      const key = row.dataset.rankKey
      if (key == null) continue
      const top = row.offsetTop
      next.set(key, top)
      if (!prev.current) continue
      const old = prev.current.get(key)
      if (old == null) {
        row.style.transition = 'none'
        row.style.opacity = '0'
        moved.push(row)
      } else if (old !== top) {
        row.style.transition = 'none'
        row.style.transform = `translateY(${old - top}px)`
        moved.push(row)
      }
    }
    prev.current = next
    if (!moved.length) return
    const frame = requestAnimationFrame(() => {
      for (const row of moved) {
        row.style.transition = 'transform var(--bar-ms, 600ms) var(--bar-ease, ease), opacity var(--bar-ms, 600ms) ease'
        row.style.transform = ''
        row.style.opacity = ''
      }
    })
    return () => cancelAnimationFrame(frame)
  })

  return ref
}
