import { useState, useEffect, useRef } from 'react'
import { adminGetBracket, adminPreviewBracket } from '@/api/brackets'
import Spinner from '@/components/ui/Spinner'
import { avatarUrl } from '@/utils/avatar'
import {
  FORMATS,
  LAYOUTS,
  THEMES,
  DEFAULT_OPTIONS,
  describeProgress,
  drawBracket,
} from '@/utils/bracketCanvas'

const INPUT = 'w-full bg-bg-raised border border-border rounded px-3 py-2 text-sm'
const LABEL = 'block text-xs uppercase tracking-wider text-text-muted mb-1'

const TOGGLES = [
  ['showSeeds', 'Seeds'],
  ['showAvatars', 'Avatars'],
  ['showChampion', 'Champion'],
  ['highlightLive', 'Mark live matches'],
  ['showRoundTitles', 'Round names'],
]

/**
 * The bracket to open on: the top cut being played right now, else the most
 * recently finished one, else whatever is first.
 */
export function pickActiveBracket(brackets = []) {
  return (
    brackets.find((b) => b.status === 'published') ||
    brackets.find((b) => b.status === 'complete') ||
    brackets[0] ||
    null
  )
}

/** Load every avatar the graphic needs. Ones that won't load are left out. */
function loadAvatars(entrants = []) {
  return Promise.all(
    entrants
      .filter((e) => e.user_id && avatarUrl(e, 128))
      .map(
        (entrant) =>
          new Promise((resolve) => {
            const img = new Image()
            // Without CORS the image would taint the canvas and block the download.
            img.crossOrigin = 'anonymous'
            img.onload = () => resolve([String(entrant.user_id), img])
            img.onerror = () => resolve(null)
            img.src = avatarUrl(entrant, 128)
          }),
      ),
  ).then((pairs) => new Map(pairs.filter(Boolean)))
}

function slugToFilename(slug, format) {
  return `${slug || 'bracket'}-${format}.png`
}

/**
 * Admin tool: render a bracket as an image to post in Discord or on socials.
 */
export default function BracketGraphic({ brackets, selectedSlug, onSelect }) {
  const canvasRef = useRef(null)
  const [data, setData] = useState(null)
  const [avatars, setAvatars] = useState(new Map())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [options, setOptions] = useState(DEFAULT_OPTIONS)

  const slug = selectedSlug || pickActiveBracket(brackets)?.slug || ''

  useEffect(() => {
    if (!slug) return undefined
    let cancelled = false
    setLoading(true)
    setError(null)
    setNotice(null)
    ;(async () => {
      try {
        const detail = await adminGetBracket(slug)
        let next = detail
        // A draft has no matches yet: show the tree its seeding would make.
        if (detail.bracket?.status === 'draft' && !detail.rounds?.length) {
          const preview = await adminPreviewBracket(slug).catch(() => null)
          next = { ...detail, rounds: preview?.rounds || [] }
        }
        if (cancelled) return
        setData(next)
        setOptions((o) => ({ ...o, startRound: null }))
        const images = await loadAvatars(next.entrants)
        if (!cancelled) setAvatars(images)
      } catch (e) {
        if (!cancelled) {
          setData(null)
          setError(e.message || 'Could not load this bracket.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [slug])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !data) return
    const { width, height } = FORMATS[options.format]
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext?.('2d')
    if (!ctx) return
    const paint = () => drawBracket(ctx, data, options, options.showAvatars ? avatars : new Map())
    paint()
    // Repaint once the site fonts are in, so the title isn't left in Georgia.
    document.fonts?.ready?.then(paint)
  }, [data, options, avatars])

  const set = (key, value) => setOptions((o) => ({ ...o, [key]: value }))

  function toBlob() {
    return new Promise((resolve, reject) => {
      const canvas = canvasRef.current
      if (!canvas?.toBlob) return reject(new Error('Nothing to save yet.'))
      try {
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Could not draw the image.'))), 'image/png')
      } catch (e) {
        reject(e)
      }
    })
  }

  async function download() {
    try {
      const blob = await toBlob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = slugToFilename(slug, options.format)
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('Image downloaded.')
    } catch (e) {
      setNotice(e.message)
    }
  }

  async function copy() {
    try {
      if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') {
        throw new Error('This browser can’t copy images — use Download instead.')
      }
      const blob = await toBlob()
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      setNotice('Copied — paste it straight into Discord.')
    } catch (e) {
      setNotice(e.message)
    }
  }

  if (!brackets?.length) return null

  const rounds = data?.rounds || []
  const hiddenFromPlayers =
    data && data.bracket?.status !== 'complete' && (data.decks_missing ?? 0) > 0

  return (
    <section className="bg-bg-surface border border-border rounded-lg p-5 space-y-4" id="bracket-graphic">
      <div>
        <h2 className="text-lg font-display">Bracket graphic</h2>
        <p className="text-xs text-text-muted">
          A picture of the top cut to post for people to follow along. It opens on the bracket
          being played now — pick another to make a graphic of that one instead.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="graphic-bracket">Bracket</label>
          <select
            id="graphic-bracket"
            className={INPUT}
            value={slug}
            onChange={(e) => onSelect(e.target.value)}
          >
            {brackets.map((b) => (
              <option key={b.slug} value={b.slug}>
                {b.name}
                {b.status === 'published' ? ' (in progress)' : b.status === 'draft' ? ' (draft)' : ' (finished)'}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-format">Size</label>
          <select
            id="graphic-format"
            className={INPUT}
            value={options.format}
            onChange={(e) => set('format', e.target.value)}
          >
            {Object.entries(FORMATS).map(([key, f]) => (
              <option key={key} value={key}>{f.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-layout">Layout</label>
          <select
            id="graphic-layout"
            className={INPUT}
            value={options.layout}
            onChange={(e) => set('layout', e.target.value)}
          >
            {Object.entries(LAYOUTS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-theme">Theme</label>
          <select
            id="graphic-theme"
            className={INPUT}
            value={options.theme}
            onChange={(e) => set('theme', e.target.value)}
          >
            {Object.entries(THEMES).map(([key, t]) => (
              <option key={key} value={key}>{t.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-start">Start from</label>
          <select
            id="graphic-start"
            className={INPUT}
            value={options.startRound ?? ''}
            onChange={(e) => set('startRound', e.target.value ? Number(e.target.value) : null)}
            disabled={rounds.length < 2}
          >
            <option value="">Whole bracket</option>
            {rounds.slice(1).map((r) => (
              <option key={r.round} value={r.round}>{r.title} on</option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-title">Title</label>
          <input
            id="graphic-title"
            className={INPUT}
            value={options.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder={data?.bracket?.name || 'Bracket name'}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="graphic-subtitle">Subtitle</label>
          <input
            id="graphic-subtitle"
            className={INPUT}
            value={options.subtitle}
            onChange={(e) => set('subtitle', e.target.value)}
            placeholder={data ? describeProgress(data) : 'Progress, filled in for you'}
          />
        </div>

        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="graphic-footer">Footer</label>
          <input
            id="graphic-footer"
            className={INPUT}
            value={options.footer}
            onChange={(e) => set('footer', e.target.value)}
            placeholder="Leave blank for none"
          />
        </div>

        <div className="sm:col-span-2 flex flex-wrap gap-x-5 gap-y-2">
          {TOGGLES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={Boolean(options[key])}
                onChange={(e) => set(key, e.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {hiddenFromPlayers && (
        <p className="text-sm text-amber-400">
          Heads up: players can’t see this tree yet — {data.decks_missing} decklist
          {data.decks_missing > 1 ? 's are' : ' is'} still missing. Posting this graphic reveals
          the draw.
        </p>
      )}

      {error && <p className="text-sm text-accent-red">{error}</p>}
      {loading && !data && <Spinner />}

      {data && (
        <div className="space-y-3">
          <canvas
            ref={canvasRef}
            aria-label={`Bracket graphic for ${data.bracket?.name || 'this bracket'}`}
            className="w-full h-auto rounded border border-border"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={download}
              className="px-4 py-2 rounded bg-secondary text-black text-sm font-medium"
            >
              Download PNG
            </button>
            <button
              type="button"
              onClick={copy}
              className="px-4 py-2 rounded border border-border text-sm"
            >
              Copy image
            </button>
            <button
              type="button"
              onClick={() => setOptions(DEFAULT_OPTIONS)}
              className="px-3 py-2 text-sm text-text-muted hover:text-text-primary"
            >
              Reset options
            </button>
            {notice && <span className="text-sm text-text-muted">{notice}</span>}
          </div>
        </div>
      )}
    </section>
  )
}
