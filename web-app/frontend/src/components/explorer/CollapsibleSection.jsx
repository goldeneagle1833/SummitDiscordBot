import { useState } from 'react'

const read = (key, fallback) => {
  try {
    const value = localStorage.getItem(key)
    return value === null ? fallback : value === '1'
  } catch {
    return fallback
  }
}

/**
 * A titled section with a ▶ arrow that folds it away. Open or closed is
 * remembered per browser when storageKey is given.
 */
export default function CollapsibleSection({
  title, storageKey, defaultOpen = true, aside, className = '', headerClassName = '', children,
}) {
  const [open, setOpen] = useState(() => (storageKey ? read(storageKey, defaultOpen) : defaultOpen))

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (!storageKey) return
    try {
      localStorage.setItem(storageKey, next ? '1' : '0')
    } catch {
      // Storage blocked: it just won't remember.
    }
  }

  return (
    <section className={className}>
      <div className={`flex flex-wrap items-baseline justify-between gap-2 ${headerClassName}`}>
        <button type="button" onClick={toggle} aria-expanded={open} className="flex items-center gap-2 text-left">
          <span className={`text-xs text-text-muted transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden="true">▶</span>
          <h2 className="text-sm font-semibold text-secondary">{title}</h2>
        </button>
        {aside}
      </div>
      {open && children}
    </section>
  )
}
