export default function Avatar({ src, alt, size = 'md', className = '' }) {
  const sizeClasses = {
    sm: 'h-8 w-8',
    md: 'h-10 w-10',
    lg: 'h-16 w-16',
    xl: 'h-24 w-24',
  }

  return (
    <div className={`${sizeClasses[size] || sizeClasses.md} rounded-full overflow-hidden bg-bg-elevated flex-shrink-0 ${className}`}>
      {src ? (
        <img
          src={src}
          alt={alt || ''}
          className="h-full w-full object-cover"
          onError={(e) => { e.target.style.display = 'none' }}
        />
      ) : (
        <div className="h-full w-full flex items-center justify-center text-text-muted">
          <svg className="h-1/2 w-1/2" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
          </svg>
        </div>
      )}
    </div>
  )
}
