export default function CollapsibleSection({ title, open, onToggle, children }) {
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
