import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

// Full screen view of a product's images, uncropped. Steps through several
// images with the arrows (buttons, keyboard or swipe). Closes with Esc, the X,
// or a click anywhere outside the image.
export default function ImageLightbox({ images, startIndex = 0, alt, onClose }) {
  const [index, setIndex] = useState(startIndex)
  const touchX = useRef(null)
  const closeRef = useRef(null)
  const count = images.length
  const many = count > 1

  const step = (delta) => setIndex((i) => (i + delta + count) % count)

  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
      else if (many && e.key === 'ArrowRight') step(1)
      else if (many && e.key === 'ArrowLeft') step(-1)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, many, count])

  // Keep the page behind from scrolling while the viewer is open
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => { document.body.style.overflow = prev }
  }, [])

  const onTouchStart = (e) => { touchX.current = e.touches[0].clientX }
  const onTouchEnd = (e) => {
    if (touchX.current == null || !many) return
    const dx = e.changedTouches[0].clientX - touchX.current
    touchX.current = null
    if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1)
  }

  const stop = (e) => e.stopPropagation()
  const arrowClass = 'absolute top-1/2 -translate-y-1/2 h-11 w-11 flex items-center justify-center rounded-full bg-black/60 text-white/90 hover:bg-black/80 hover:text-secondary transition-colors'

  return createPortal(
    <div
      className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/90"
      role="dialog"
      aria-modal="true"
      aria-label={`${alt} image viewer`}
      onClick={onClose}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <img
        src={images[index]}
        alt={alt}
        onClick={stop}
        className="max-w-[calc(100vw-2rem)] max-h-[calc(100vh-6rem)] sm:max-w-[calc(100vw-9rem)] object-contain select-none shadow-2xl"
        draggable={false}
      />

      <button
        ref={closeRef}
        type="button"
        onClick={(e) => { stop(e); onClose() }}
        aria-label="Close image viewer"
        className="absolute top-3 right-3 h-11 w-11 flex items-center justify-center rounded-full bg-black/60 text-white/90 hover:bg-black/80 hover:text-secondary transition-colors"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>

      {many && (
        <>
          <button
            type="button"
            onClick={(e) => { stop(e); step(-1) }}
            aria-label="Previous image"
            className={`${arrowClass} left-2 sm:left-5`}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <button
            type="button"
            onClick={(e) => { stop(e); step(1) }}
            aria-label="Next image"
            className={`${arrowClass} right-2 sm:right-5`}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-black/60 text-sm text-white/90" onClick={stop}>
            {index + 1} / {count}
          </div>
        </>
      )}
    </div>,
    document.body,
  )
}
