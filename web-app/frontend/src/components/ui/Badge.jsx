export default function Badge({ children, variant = 'default', className = '' }) {
  const variants = {
    default: 'bg-bg-elevated text-text-muted',
    primary: 'bg-primary/20 text-primary',
    secondary: 'bg-secondary/20 text-secondary',
    success: 'bg-accent-green/20 text-accent-green',
    danger: 'bg-accent-red/20 text-accent-red',
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${variants[variant] || variants.default} ${className}`}>
      {children}
    </span>
  )
}
