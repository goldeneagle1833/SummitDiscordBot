import { useState } from 'react'

export default function AdminCollapsible({ title, subtitle, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left group"
      >
        <span className={`text-xs text-text-muted transition-transform ${open ? 'rotate-90' : ''}`}>&#9654;</span>
        <div>
          <h2 className="text-lg font-semibold text-text-primary group-hover:text-secondary transition-colors">{title}</h2>
          {subtitle && <p className="text-xs text-text-muted">{subtitle}</p>}
        </div>
      </button>
      {open && <div className="mt-4">{children}</div>}
    </section>
  )
}
