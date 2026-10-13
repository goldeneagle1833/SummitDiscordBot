import { useRef } from 'react'
import FramedImage, { DEFAULT_FRAMING } from './FramedImage'

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

// Live previews of a product image at the store card's size, with drag to
// reposition and sliders for position and zoom.
export default function ImageFramer({ url, framing, onChange }) {
  const f = { ...DEFAULT_FRAMING, ...framing }
  const boxRef = useRef(null)
  const imgRef = useRef(null)
  const drag = useRef(null)

  const update = (patch) => onChange({ ...f, ...patch })

  // How far the image can slide past the box edges, in pixels
  const overflow = () => {
    const box = boxRef.current?.getBoundingClientRect()
    const img = imgRef.current
    if (!box || !img?.naturalWidth) return { x: 1, y: 1 }
    const cover = Math.max(box.width / img.naturalWidth, box.height / img.naturalHeight)
    return {
      x: Math.max(img.naturalWidth * cover * f.zoom - box.width, 1),
      y: Math.max(img.naturalHeight * cover * f.zoom - box.height, 1),
    }
  }

  const onPointerDown = (e) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const room = overflow()
    drag.current = { px: e.clientX, py: e.clientY, x: f.x, y: f.y, roomX: room.x, roomY: room.y }
  }
  const onPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    // Dragging the picture right shows more of its left side
    update({
      x: Math.round(clamp(d.x - ((e.clientX - d.px) / d.roomX) * 100, 0, 100)),
      y: Math.round(clamp(d.y - ((e.clientY - d.py) / d.roomY) * 100, 0, 100)),
    })
  }
  const endDrag = () => {
    drag.current = null
  }

  const slider = (label, key, min, max, step) => (
    <label className="flex items-center gap-2 text-xs text-text-muted">
      <span className="w-20 shrink-0">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={f[key]}
        onChange={(e) => update({ [key]: Number(e.target.value) })}
        aria-label={label}
        className="flex-1 accent-secondary"
      />
    </label>
  )

  return (
    <div className="rounded border border-border bg-bg-elevated/40 p-3 space-y-3">
      <p className="text-xs text-text-muted">
        Drag the picture or use the sliders to choose what shows on the store card.
      </p>
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1 max-w-full">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Desktop card</p>
          <div
            ref={boxRef}
            data-testid="framing-preview"
            className="w-[440px] max-w-full h-48 rounded border border-border cursor-grab active:cursor-grabbing touch-none"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            <FramedImage src={url} alt="Store card preview" framing={f} imgRef={imgRef} className="w-full h-full" />
          </div>
        </div>
        <div className="space-y-1 max-w-full">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Phone card</p>
          <FramedImage src={url} alt="" framing={f} className="w-[340px] max-w-full h-48 rounded border border-border" />
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {slider('Left / right', 'x', 0, 100, 1)}
        {slider('Up / down', 'y', 0, 100, 1)}
        {slider('Zoom', 'zoom', 1, 3, 0.05)}
      </div>
      <button
        type="button"
        onClick={() => onChange({ ...DEFAULT_FRAMING })}
        className="text-xs text-primary hover:underline"
      >
        Reset to centered
      </button>
    </div>
  )
}
