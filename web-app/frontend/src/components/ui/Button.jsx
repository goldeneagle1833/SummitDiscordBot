import { Link } from 'react-router-dom'

export default function Button({
  children,
  variant = 'primary',
  to,
  href,
  className = '',
  ...props
}) {
  const base = 'inline-flex items-center justify-center px-4 py-2 rounded-soft font-medium transition-colors duration-fast focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed'

  const variants = {
    primary: 'bg-primary text-bg-dark hover:bg-primary-dark',
    secondary: 'bg-secondary text-bg-dark hover:bg-secondary-dark',
    danger: 'bg-accent-red text-white hover:opacity-90',
    ghost: 'bg-transparent text-text-muted hover:bg-bg-elevated hover:text-text',
  }

  const classes = `${base} ${variants[variant] || variants.primary} ${className}`

  if (to) return <Link to={to} className={classes} {...props}>{children}</Link>
  if (href) return <a href={href} className={classes} {...props}>{children}</a>

  return <button className={classes} {...props}>{children}</button>
}
