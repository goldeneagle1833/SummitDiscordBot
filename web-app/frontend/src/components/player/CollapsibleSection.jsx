/**
 * A titled profile section. With onToggle it collapses behind its title;
 * without one (inside a profile tab) it is always open under a plain heading.
 */
export default function CollapsibleSection({ title, open, onToggle, children }) {
  if (!onToggle) {
    return (
      <section className="bg-bg-surface border border-border rounded-xl p-5">
        <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-4">{title}</h2>
        {children}
      </section>
    )
  }
  return (
    <section>
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-lg font-semibold text-text-primary mb-3 hover:text-secondary transition-colors w-full text-left"
      >
        <span className={`text-xs transition-transform ${open ? 'rotate-90' : ''}`}>&#9654;</span>
        {title}
      </button>
      {open && children}
    </section>
  )
}
