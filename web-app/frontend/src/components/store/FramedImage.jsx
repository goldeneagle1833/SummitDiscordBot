import { useEffect, useRef, useState } from 'react'

// A product image placed in its box by the framing saved in Store Admin:
// { x, y, zoom }. x/y are percents like object-position. zoom is relative
// to filling the box (1 = cover, the old default); below 1 zooms out, down
// to showing the whole image with the box color around it.
export const DEFAULT_FRAMING = { x: 50, y: 50, zoom: 1 }
export const MIN_ZOOM = 0.25
export const MAX_ZOOM = 3

// Pixel size and offset of the image inside a cw x ch box
export function framedLayout(cw, ch, nw, nh, framing) {
  const { x, y, zoom } = { ...DEFAULT_FRAMING, ...framing }
  const cover = Math.max(cw / nw, ch / nh)
  const contain = Math.min(cw / nw, ch / nh)
  const scale = Math.max(cover * zoom, contain)
  const w = nw * scale
  const h = nh * scale
  return { w, h, left: ((cw - w) * x) / 100, top: ((ch - h) * y) / 100 }
}

// CSS-only fallback until the image and box are measured
export function framingStyle(framing) {
  const { x, y, zoom } = { ...DEFAULT_FRAMING, ...framing }
  return {
    objectPosition: `${x}% ${y}%`,
    transformOrigin: `${x}% ${y}%`,
    transform: zoom > 1 ? `scale(${zoom})` : undefined,
  }
}

export default function FramedImage({ src, alt, framing, className = '', imgRef, onLoad }) {
  const boxRef = useRef(null)
  const [box, setBox] = useState(null)
  const [natural, setNatural] = useState(null)

  useEffect(() => {
    const el = boxRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setBox(width && height ? { w: width, h: height } : null)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const handleLoad = (e) => {
    const { naturalWidth, naturalHeight } = e.currentTarget
    setNatural(naturalWidth && naturalHeight ? { w: naturalWidth, h: naturalHeight } : null)
    onLoad?.(e)
  }

  const layout = box && natural ? framedLayout(box.w, box.h, natural.w, natural.h, framing) : null
  const style = layout
    ? { position: 'absolute', width: layout.w, height: layout.h, left: layout.left, top: layout.top, maxWidth: 'none' }
    : framingStyle(framing)

  return (
    <div ref={boxRef} className={`relative overflow-hidden bg-bg-elevated ${className}`}>
      <img
        ref={imgRef}
        src={src}
        alt={alt}
        onLoad={handleLoad}
        draggable={false}
        className={layout ? 'select-none' : 'w-full h-full object-cover select-none'}
        style={style}
      />
    </div>
  )
}
