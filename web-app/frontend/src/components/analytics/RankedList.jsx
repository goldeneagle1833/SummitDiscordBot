import { useLayoutEffect, useRef, useState } from 'react'

/**
 * Rows that slide smoothly when their rank changes.
 *
 * Each row is absolutely placed at `rank × row height` and moved with a CSS
 * transform, so a rank change mid-slide carries on from wherever the row is
 * (no snapping) and DOM order never changes. Rows past `visible` slide out
 * under the clipped bottom edge instead of vanishing. Until the row height
 * is measured (first paint, or no layout as in tests) rows render in flow.
 *
 * `items` must already be in rank order; `itemKey` gives each a stable key.
 */
export default function RankedList({ items, itemKey, renderItem, gap = 8, visible }) {
  const ref = useRef(null)
  const [rowH, setRowH] = useState(0)

  useLayoutEffect(() => {
    const list = ref.current
    if (!list) return
    let h = 0
    for (const row of list.children) h = Math.max(h, row.offsetHeight)
    if (h && h !== rowH) setRowH(h)
  })

  const keys = items.map(itemKey)
  const rank = new Map(keys.map((k, i) => [k, i]))
  const shown = visible == null ? items.length : Math.min(visible, items.length)
  const placed = rowH > 0
  const step = rowH + gap
  // Stable DOM order once placed: only the transform says where a row sits
  const order = placed ? [...items].sort((a, b) => (itemKey(a) < itemKey(b) ? -1 : 1)) : items.slice(0, shown)

  return (
    <div
      ref={ref}
      className={placed ? 'timeline-list relative overflow-hidden' : undefined}
      style={placed ? { height: shown ? shown * step - gap : 0 } : undefined}
    >
      {order.map((item) => {
        const key = itemKey(item)
        const i = rank.get(key)
        return (
          <div
            key={key}
            data-rank-key={key}
            className={placed ? 'timeline-row absolute inset-x-0 top-0' : undefined}
            style={placed
              ? { transform: `translateY(${i * step}px)`, opacity: i < shown ? 1 : 0 }
              : { marginTop: i ? gap : 0 }}
            aria-hidden={i >= shown || undefined}
          >
            {renderItem(item, i)}
          </div>
        )
      })}
    </div>
  )
}
