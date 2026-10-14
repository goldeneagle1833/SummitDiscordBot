import { useRef } from 'react'
import FramedImage, { DEFAULT_FRAMING, MIN_ZOOM, MAX_ZOOM, framedLayout } from './FramedImage'

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

// Live preview of a product image in the store card's frame, with drag to
// reposition and sliders for position and zoom.
export default function ImageFramer({ url, framing, onChange }) {
  const f = { ...DEFAULT_FRAMING, ...framing }
  const boxRef = useRef(null)
  const imgRef = useRef(null)
  const drag = useRef(null)

  const update = (patch) => onChange({ ...f, ...patch })

  // Pixels of drag that move the image from one edge position to the
  // other (negative when the image is bigger than the box)
  const travel = () => {
    const box = boxRef.current?.getBoundingClientRect()
    const img = imgRef.current
    if (!box?.width || !img?.naturalWidth) return { x: -1, y: -1 }
    const { w, h } = framedLayout(box.width, box.height, img.naturalWidth, img.naturalHeight, f)
    const nonZero = (v) => (Math.abs(v) < 1 ? (v < 0 ? -1 : 1) : v)
    return { x: nonZero(box.width - w), y: nonZero(box.height - h) }
  }

  // Zoom at which the whole picture just fits inside the card
  const fitWhole = () => {
    const box = boxRef.current?.getBoundingClientRect()
    const img = imgRef.current
    if (!box?.width || !img?.naturalWidth) return update({ zoom: 0.5, x: 50, y: 50 })
    const rx = box.width / img.naturalWidth
    const ry = box.height / img.naturalHeight
    const zoom = Math.round((Math.min(rx, ry) / Math.max(rx, ry)) * 100) / 100
    update({ zoom: Math.max(MIN_ZOOM, zoom), x: 50, y: 50 })
  }

  const onPointerDown = (e) => {
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    const t = travel()
    drag.current = { px: e.clientX, py: e.clientY, x: f.x, y: f.y, tx: t.x, ty: t.y }
  }
  const onPointerMove = (e) => {
    const d = drag.current
    if (!d) return
    // The picture follows the pointer
    update({
      x: Math.round(clamp(d.x + ((e.clientX - d.px) / d.tx) * 100, 0, 100)),
      y: Math.round(clamp(d.y + ((e.clientY - d.py) / d.ty) * 100, 0, 100)),
    })
  }
  const endDrag = () => {
    drag.current = null
  }

  const slider = (label, key, min, max, step, shown) => (
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
        className="flex-1 min-w-0 accent-secondary"
      />
      {shown && <span className="w-10 text-right tabular-nums">{shown}</span>}
    </label>
  )

  return (
    <div className="min-w-0 rounded border border-border bg-bg-elevated/40 p-3 space-y-3">
      <p className="text-xs text-text-muted">
        Drag the picture to move it. Use Zoom to go closer, or below 100% to show more of it. Any empty space shows as black. Store cards look exactly like this on every screen size.
      </p>
      <div
        ref={boxRef}
        data-testid="framing-preview"
        className="w-full max-w-md aspect-[3/2] rounded border border-border cursor-grab active:cursor-grabbing touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <FramedImage src={url} alt="Store card preview" framing={f} imgRef={imgRef} className="w-full h-full" />
      </div>
      {slider('Zoom', 'zoom', MIN_ZOOM, MAX_ZOOM, 0.05, `${Math.round(f.zoom * 100)}%`)}
      <div className="grid gap-2 sm:grid-cols-2">
        {slider('Left / right', 'x', 0, 100, 1)}
        {slider('Up / down', 'y', 0, 100, 1)}
      </div>
      <div className="flex flex-wrap gap-4">
        <button
          type="button"
          onClick={fitWhole}
          className="text-xs text-primary hover:underline"
        >
          Fit whole image
        </button>
        <button
          type="button"
          onClick={() => onChange({ ...DEFAULT_FRAMING })}
          className="text-xs text-primary hover:underline"
        >
          Reset to fill the card
        </button>
      </div>
    </div>
  )
}
