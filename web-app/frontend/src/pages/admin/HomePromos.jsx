import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { get, post } from '@/api/client'
import AdminCollapsible from '@/components/admin/AdminCollapsible'
import BannersSection from '@/components/admin/BannersSection'
import { BUILT_IN_SLOTS, bannerSlide, loadPromoSlides, orderBySlots } from '@/utils/promoSlides'

// Admin > Home Promos: every slide that can show in the home page carousel,
// in carousel order. Drag the grip (or use the arrows) to reorder and flip
// the switch to turn one off. Changes save straight away.

const BANNER_SOURCES = {
  'content-bot': 'Shared in Discord · auto, 24 hours',
  'meta-report': 'Meta Report · auto',
}

function bannerSource(b) {
  return BANNER_SOURCES[b.created_by] || `Custom banner${b.created_by ? ` by ${b.created_by}` : ''}`
}

function expiresIn(expiresAt) {
  const ms = new Date(`${expiresAt.replace(' ', 'T')}Z`) - Date.now()
  if (!Number.isFinite(ms)) return ''
  const hours = Math.round(ms / 3600000)
  if (hours < 1) return 'ends within the hour'
  if (hours < 48) return `ends in ${hours} h`
  return `ends in ${Math.round(hours / 24)} days`
}

/** Rows for every slot, in the built-in default order, before the saved order. */
export function buildRows(slides, banners, layout) {
  const bySlot = new Map(slides.map(s => [s.slot, s]))
  const hidden = new Set(layout?.hidden || [])
  const builtIn = (slot) => {
    const meta = BUILT_IN_SLOTS.find(m => m.slot === slot)
    const slide = bySlot.get(slot) || null
    return { slot, label: meta.label, source: meta.source, slide, on: !hidden.has(slot), banner: null }
  }
  const bannerRows = banners.map(b => ({
    slot: `promo-${b.id}`, label: b.title, source: bannerSource(b),
    slide: bannerSlide(b), on: !!b.active, banner: b,
  }))
  const rows = [
    builtIn('kudos'), builtIn('new-event'), builtIn('new-article'),
    ...bannerRows,
    builtIn('spotlight'), builtIn('event-spotlight'), builtIn('staff-pick'),
  ]
  return orderBySlots(rows, layout?.order)
}

function move(list, from, to) {
  const next = [...list]
  const [row] = next.splice(from, 1)
  next.splice(to, 0, row)
  return next
}

function GripIcon() {
  return (
    <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
      {[6, 10, 14].map((y) => [7, 13].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.5" />))}
    </svg>
  )
}

function Switch({ on, onClick, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors ${
        on ? 'bg-accent-green/80 border-accent-green' : 'bg-bg-elevated border-border'}`}
    >
      <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-6' : 'translate-x-1'}`} />
    </button>
  )
}

export default function HomePromos() {
  usePageTitle('Home Promos')
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [dragSlot, setDragSlot] = useState(null)
  const rowsRef = useRef(rows)
  rowsRef.current = rows
  const dragStart = useRef(null)

  const load = useCallback(() => {
    Promise.all([
      loadPromoSlides(),
      get('/api/analytics/promo-layout'),
    ]).then(([{ slides }, d]) => {
      if (!d.success) throw new Error(d.error || 'Could not load the promo list')
      setRows(buildRows(slides, d.banners || [], d.layout))
    }).catch((e) => setError(e.message || 'Could not load the promo list'))
  }, [])
  useEffect(load, [load])

  const save = async (list) => {
    setSaved(false)
    setError(null)
    try {
      const d = await post('/api/analytics/promo-layout', {
        order: list.map(r => r.slot),
        off: list.filter(r => !r.on).map(r => r.slot),
      })
      if (!d.success) throw new Error(d.error || 'Save failed')
      setSaved(true)
    } catch (e) {
      setError(e.message || 'Save failed')
      load()
    }
  }

  const nudge = (i, dir) => {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const next = move(rows, i, j)
    setRows(next)
    save(next)
  }

  const toggle = (i) => {
    const next = rows.map((r, k) => (k === i ? { ...r, on: !r.on } : r))
    setRows(next)
    save(next)
  }

  const onGripDown = (e, slot) => {
    if (e.button != null && e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture?.(e.pointerId)
    dragStart.current = { slot, order: rowsRef.current.map(r => r.slot).join() }
    setDragSlot(slot)
    document.body.style.userSelect = 'none'
  }
  const onGripMove = (e) => {
    if (!dragStart.current) return
    const { clientX: x, clientY: y } = e
    if (y < 120) window.scrollBy?.(0, -14)
    else if (y > window.innerHeight - 80) window.scrollBy?.(0, 14)
    const target = document.elementFromPoint?.(x, y)?.closest?.('[data-slot]')?.dataset.slot
    if (target && target !== dragStart.current.slot) {
      setRows((list) => {
        const from = list.findIndex(r => r.slot === dragStart.current.slot)
        const to = list.findIndex(r => r.slot === target)
        return from < 0 || to < 0 ? list : move(list, from, to)
      })
    }
  }
  const onGripUp = () => {
    const start = dragStart.current
    dragStart.current = null
    setDragSlot(null)
    document.body.style.userSelect = ''
    if (start && rowsRef.current.map(r => r.slot).join() !== start.order) save(rowsRef.current)
  }

  // Slide numbers as visitors see them: only slides that are on and have something to show
  let shown = 0
  const numbers = (rows || []).map(r => (r.on && r.slide ? ++shown : null))
  const arrowCls = 'block px-1.5 py-0.5 leading-none text-text-muted hover:text-text-primary disabled:opacity-20 disabled:cursor-default'

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <Link to="/admin" className="text-xs text-text-muted hover:text-secondary">&larr; Admin</Link>
        <h1 className="text-2xl font-display text-secondary mt-1">Home Promos</h1>
        <p className="text-sm text-text-muted mt-1">
          Every slide in the home page carousel, in the order it plays. Drag the grip or use the arrows to move one,
          and flip the switch to turn it off. Changes save straight away.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {rows && <span className="text-text-primary"><strong>{shown}</strong> showing on the home page now</span>}
        {saved && <span className="text-accent-green text-xs">Saved</span>}
        {error && <span className="text-accent-red text-xs">{error}</span>}
      </div>

      {!rows && !error && <p className="text-sm text-text-muted">Loading…</p>}

      {rows && (
        <ol className="space-y-2">
          {rows.map((r, i) => {
            const empty = !r.slide
            const status = !r.on ? 'Off' : empty ? 'Nothing to show right now' : `Slide ${numbers[i]}`
            return (
              <li
                key={r.slot}
                data-slot={r.slot}
                className={`flex items-center gap-2 sm:gap-3 rounded-soft border bg-bg-surface p-2 sm:p-3 ${
                  dragSlot === r.slot ? 'border-primary bg-primary/10' : 'border-border'} ${r.on ? '' : 'opacity-60'}`}
              >
                <div className="flex items-center select-none shrink-0">
                  <button
                    type="button"
                    onPointerDown={(e) => onGripDown(e, r.slot)}
                    onPointerMove={onGripMove}
                    onPointerUp={onGripUp}
                    onPointerCancel={onGripUp}
                    style={{ touchAction: 'none' }}
                    className={`p-1 rounded text-text-muted hover:text-text-primary ${dragSlot === r.slot ? 'cursor-grabbing' : 'cursor-grab'}`}
                    aria-label={`Drag to reorder ${r.label}`}
                    title="Drag to reorder"
                  >
                    <GripIcon />
                  </button>
                  <div className="flex flex-col">
                    <button type="button" onClick={() => nudge(i, -1)} disabled={i === 0}
                      className={arrowCls} aria-label={`Move ${r.label} up`}>▲</button>
                    <button type="button" onClick={() => nudge(i, 1)} disabled={i === rows.length - 1}
                      className={arrowCls} aria-label={`Move ${r.label} down`}>▼</button>
                  </div>
                </div>

                <div className="hidden sm:block h-12 w-20 shrink-0 overflow-hidden rounded border border-border bg-bg-elevated">
                  {r.slide?.thumbnail && (
                    <img src={r.slide.thumbnail} alt="" className="h-full w-full object-cover"
                      onError={(e) => { e.target.style.display = 'none' }} />
                  )}
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className={`text-[11px] font-semibold uppercase tracking-wider ${
                      !r.on ? 'text-text-muted' : empty ? 'text-text-muted' : 'text-accent-green'}`}>{status}</span>
                    {r.slide?.badge && (
                      <span className="text-[10px] font-semibold px-1.5 rounded-full border border-border text-text-muted uppercase">
                        {r.slide.badge}
                      </span>
                    )}
                  </div>
                  <div className="text-sm font-semibold text-text-primary line-clamp-2 sm:truncate">
                    {r.banner ? r.label : r.slide?.title || r.label}
                  </div>
                  <div className="text-xs text-text-muted truncate">
                    {r.banner || empty ? r.source : `${r.label} · ${r.source}`}
                    {r.banner && ` · ${expiresIn(r.banner.expires_at)}`}
                  </div>
                </div>

                <Switch on={r.on} onClick={() => toggle(i)} label={`${r.on ? 'Turn off' : 'Turn on'} ${r.label}`} />
              </li>
            )
          })}
        </ol>
      )}

      <p className="text-xs text-text-muted">
        Slides that fill themselves in (Player of the Day, newest article and so on) keep their place and switch when
        their content changes. A newly shared video or new banner shows up in its usual spot until you move it.
      </p>

      <AdminCollapsible title="Create or delete banners" subtitle="Add your own slide with a link, image and end date">
        <BannersSection onChange={load} />
      </AdminCollapsible>
    </div>
  )
}
