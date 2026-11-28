import { useEffect, useRef, useState } from 'react'
import { cardPicturePreviewUrl, getProfilePicture, setProfilePicture, uploadProfilePicture } from '@/api/players'
import { CardSearch } from '@/components/player/ShowcaseModal'

const MAX_BYTES = 5 * 1024 * 1024
// Bigger phone photos are shrunk in the browser before upload
const SHRINK_OVER = 4 * 1024 * 1024
const SHRINK_TO = 2000
const BOX = 240 // cropper size, px

function Circle({ children, className = '' }) {
  return (
    <div className={`w-24 h-24 shrink-0 rounded-full border-[3px] border-secondary bg-bg-raised overflow-hidden ${className}`}>
      {children}
    </div>
  )
}

function Option({ id, label, hint, checked, onChange }) {
  return (
    <label
      htmlFor={id}
      className={`flex-1 min-w-[90px] cursor-pointer rounded-lg border px-3 py-2 text-sm text-center transition-colors ${
        checked ? 'border-secondary bg-bg-raised text-text-primary' : 'border-border text-text-muted hover:text-text-primary'
      }`}
    >
      <input id={id} type="radio" name="picture-kind" className="sr-only" checked={checked} onChange={onChange} />
      <span className="block font-semibold">{label}</span>
      <span className="block text-[11px] leading-tight">{hint}</span>
    </label>
  )
}

/** Shrink a big photo so it uploads quickly and stays under the 5 MB limit. */
async function shrink(file, img) {
  if (file.size <= SHRINK_OVER) return file
  const scale = Math.min(1, SHRINK_TO / Math.max(img.naturalWidth, img.naturalHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(img.naturalWidth * scale)
  canvas.height = Math.round(img.naturalHeight * scale)
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9))
  if (!blob) return file
  return new File([blob], 'picture.jpg', { type: 'image/jpeg' })
}

/**
 * Drag to move and slide to zoom inside a round frame. Reports the visible
 * square as fractions of the picture: { x, y, size } (size of the shorter edge).
 */
export function Cropper({ src, onCrop }) {
  const [natural, setNatural] = useState(null)
  const [zoom, setZoom] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const drag = useRef(null)

  const base = natural ? BOX / Math.min(natural.w, natural.h) : 1
  const w = natural ? natural.w * base * zoom : BOX
  const h = natural ? natural.h * base * zoom : BOX
  const clamp = (p) => ({
    x: Math.min(0, Math.max(BOX - w, p.x)),
    y: Math.min(0, Math.max(BOX - h, p.y)),
  })

  useEffect(() => {
    setPos((p) => clamp(p))
  }, [zoom, natural]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!natural) return
    onCrop({ x: -pos.x / w, y: -pos.y / h, size: 1 / zoom })
  }, [pos, zoom, natural]) // eslint-disable-line react-hooks/exhaustive-deps

  const onLoad = (e) => {
    const nw = e.currentTarget.naturalWidth
    const nh = e.currentTarget.naturalHeight
    const b = BOX / Math.min(nw, nh)
    setNatural({ w: nw, h: nh })
    setZoom(1)
    setPos({ x: (BOX - nw * b) / 2, y: (BOX - nh * b) / 2 })
  }

  // Zoom around the middle of the frame, so what's centred stays centred
  const zoomTo = (z) => {
    if (natural) {
      const ratio = z / zoom
      const c = BOX / 2
      setPos({ x: c - (c - pos.x) * ratio, y: c - (c - pos.y) * ratio })
    }
    setZoom(z)
  }

  const down = (e) => {
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { sx: e.clientX, sy: e.clientY, start: pos }
  }
  const move = (e) => {
    if (!drag.current) return
    const { sx, sy, start } = drag.current
    setPos(clamp({ x: start.x + e.clientX - sx, y: start.y + e.clientY - sy }))
  }
  const up = () => {
    drag.current = null
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className="relative overflow-hidden rounded-lg bg-black cursor-grab active:cursor-grabbing select-none"
        style={{ width: BOX, height: BOX, touchAction: 'none' }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        aria-label="Drag to move the picture"
      >
        <img
          src={src}
          alt=""
          draggable={false}
          onLoad={onLoad}
          className="absolute max-w-none pointer-events-none"
          style={{ left: pos.x, top: pos.y, width: w, height: h }}
        />
        {/* Darken what falls outside the round picture */}
        <div
          className="absolute inset-0 pointer-events-none rounded-full"
          style={{ boxShadow: '0 0 0 9999px rgba(0,0,0,0.6)', border: '2px solid rgba(255,255,255,0.8)' }}
        />
      </div>
      <label className="flex items-center gap-3 text-xs text-text-muted w-full max-w-[240px]">
        Zoom
        <input
          type="range"
          min="1"
          max="4"
          step="0.01"
          value={zoom}
          onChange={(e) => zoomTo(Number(e.target.value))}
          className="flex-1 accent-secondary"
          aria-label="Zoom"
        />
      </label>
      <p className="text-xs text-text-muted">Drag the picture to move it.</p>
    </div>
  )
}

/**
 * The owner's picture editor: their Discord picture (the default), art from a
 * card, or a picture they upload. Moderators and admins open it from the
 * profile to put a picture back to Discord's.
 */
export default function ProfilePictureModal({ playerId, onClose, onSaved }) {
  const [state, setState] = useState(null)
  const [kind, setKind] = useState('discord')
  const [card, setCard] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [crop, setCrop] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const previewImg = useRef(null)

  useEffect(() => {
    let live = true
    getProfilePicture(playerId)
      .then((d) => {
        if (!live) return
        setState(d)
        setKind(d.kind)
        if (d.kind === 'card' && d.card) setCard({ name: d.card, image: null, current: d.url })
      })
      .catch((err) => live && setError(err.message || 'Could not load your picture'))
    return () => {
      live = false
    }
  }, [playerId])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])

  const pickFile = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    if (!f.type.startsWith('image/')) {
      setError('Pick a picture (JPG, PNG, WEBP or GIF).')
      return
    }
    setError(null)
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }

  const unchanged =
    (kind === 'discord' && state?.kind === 'discord') ||
    (kind === 'card' && (!card || (state?.kind === 'card' && card.name === state.card))) ||
    (kind === 'upload' && !file)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      let result
      if (kind === 'upload') {
        let toSend = file
        if (previewImg.current) toSend = await shrink(file, previewImg.current)
        if (toSend.size > MAX_BYTES) throw new Error('That picture is over 5 MB. Try a smaller one.')
        result = await uploadProfilePicture(playerId, toSend, crop)
      } else if (kind === 'card') {
        result = await setProfilePicture(playerId, { kind: 'card', card: card.name })
      } else {
        result = await setProfilePicture(playerId, { kind: 'discord' })
      }
      onSaved?.(result)
      onClose()
    } catch (err) {
      setError(err.message || 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  // The exact round crop the server will save, before saving
  const cardSrc = card?.image ? cardPicturePreviewUrl(playerId, card.name) : null

  return (
    <div className="fixed inset-0 z-[1100] flex items-start sm:items-center justify-center bg-black/60 overflow-y-auto" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Profile picture"
        className="bg-bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4 my-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text-primary mb-1">Profile Picture</h3>
        <p className="text-sm text-text-muted mb-4">Everyone who visits your profile sees it.</p>

        {!state && !error && <p className="text-sm text-text-muted">Loading…</p>}

        {state && (
          <>
            <div className="flex gap-2 mb-5" role="radiogroup" aria-label="Picture">
              <Option id="pic-discord" label="Discord" hint="Your Discord picture" checked={kind === 'discord'} onChange={() => setKind('discord')} />
              <Option id="pic-card" label="Card art" hint="Art from a card" checked={kind === 'card'} onChange={() => setKind('card')} />
              <Option id="pic-upload" label="Upload" hint="Your own picture" checked={kind === 'upload'} onChange={() => setKind('upload')} />
            </div>

            {kind === 'discord' && (
              <div className="flex items-center gap-4">
                <Circle>
                  {state.discord_url ? <img src={state.discord_url} alt="" className="w-full h-full object-cover" /> : null}
                </Circle>
                <p className="text-sm text-text-muted">
                  {state.discord_url
                    ? 'The picture from your Discord account. It changes when you change it on Discord and log in again.'
                    : 'You have no Discord picture, so your initials show.'}
                </p>
              </div>
            )}

            {kind === 'card' && (
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <Circle>
                    {cardSrc ? (
                      <img src={cardSrc} alt={`${card.name} art`} className="w-full h-full object-cover" />
                    ) : card?.current ? (
                      <img src={card.current} alt="" className="w-full h-full object-cover" />
                    ) : null}
                  </Circle>
                  <p className="text-sm text-text-muted">
                    {card ? <>Art from <strong className="text-text-primary">{card.name}</strong>. Visitors see the card name when they point at your picture.</> : 'Search for a card and we use its art.'}
                  </p>
                </div>
                <div>
                  <label htmlFor="picture-card" className="block text-xs text-text-muted mb-1">Card</label>
                  <CardSearch value={card?.image ? card : null} onChange={setCard} inputId="picture-card" />
                </div>
              </div>
            )}

            {kind === 'upload' && (
              <div className="space-y-3">
                {preview ? (
                  <>
                    <Cropper src={preview} onCrop={setCrop} />
                    {/* Hidden full-size copy, used to shrink big photos before upload */}
                    <img ref={previewImg} src={preview} alt="" className="hidden" />
                  </>
                ) : state.kind === 'upload' ? (
                  <div className="flex items-center gap-4">
                    <Circle><img src={state.url} alt="" className="w-full h-full object-cover" /></Circle>
                    <p className="text-sm text-text-muted">Your current picture. Pick a new one to replace it.</p>
                  </div>
                ) : null}
                <label className="inline-flex items-center justify-center w-full h-11 rounded-lg border border-dashed border-border text-sm text-text-primary hover:border-secondary cursor-pointer">
                  <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="sr-only" onChange={pickFile} />
                  {preview ? 'Pick a different picture' : 'Choose a picture'}
                </label>
                <p className="text-xs text-text-muted">
                  JPG, PNG, WEBP or GIF up to 5 MB. Keep it friendly: moderators can remove pictures that break the community rules.
                </p>
              </div>
            )}
          </>
        )}

        {error && <p className="text-sm text-accent-red mt-4">{error}</p>}

        <div className="flex justify-end gap-2 mt-6">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm bg-bg-raised border border-border rounded hover:border-secondary">
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!state || saving || unchanged}
            className="px-3 py-1.5 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
