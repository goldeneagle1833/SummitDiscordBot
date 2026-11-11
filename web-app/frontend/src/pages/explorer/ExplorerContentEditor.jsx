import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import Spinner from '@/components/ui/Spinner'
import { saveSiteContent, uploadSiteImages } from '@/api/explorer'
import { ES_PATHS, ES_LOGO } from '@/utils/explorerSite'
import SiteText from '@/components/explorer/SiteText'
import useSiteContent from './useSiteContent'

const inputCls = 'w-full border rounded-md px-3 py-2 text-sm'

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="block text-sm font-semibold mb-1">{label}</span>
      {hint && <span className="block text-xs es-muted mb-1.5">{hint}</span>}
      {children}
    </label>
  )
}

/** Upload button plus thumbnails you can reorder and remove. */
function PictureList({ images, onChange, max = 12, single = false }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const pick = async (e) => {
    const files = [...(e.target.files || [])]
    e.target.value = ''
    if (!files.length) return
    setBusy(true)
    setError(null)
    try {
      const { urls } = await uploadSiteImages(files.slice(0, single ? 1 : max - images.length))
      onChange(single ? urls.slice(0, 1) : [...images, ...urls].slice(0, max))
    } catch (err) {
      setError(err.message || 'Upload failed')
    }
    setBusy(false)
  }
  const move = (i, by) => {
    const next = [...images]
    const [item] = next.splice(i, 1)
    next.splice(i + by, 0, item)
    onChange(next)
  }
  const full = !single && images.length >= max
  return (
    <div>
      {images.length > 0 && (
        <ul className="flex flex-wrap gap-2 mb-2">
          {images.map((src, i) => (
            <li key={src} className="relative w-28 rounded-md overflow-hidden border border-[color:var(--es-rule)] bg-[color:var(--es-card)]">
              <img src={src} alt="" className="w-full aspect-[4/3] object-cover" />
              <div className="flex justify-between text-xs">
                {!single && <button type="button" className="px-2 py-1 disabled:opacity-30" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move picture left">←</button>}
                <button type="button" className="px-2 py-1 text-red-400" onClick={() => onChange(images.filter((_, j) => j !== i))}>Remove</button>
                {!single && <button type="button" className="px-2 py-1 disabled:opacity-30" disabled={i === images.length - 1} onClick={() => move(i, 1)} aria-label="Move picture right">→</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {!full && (
        <label className={`es-btn-ghost text-sm cursor-pointer ${busy ? 'opacity-60 pointer-events-none' : ''}`}>
          <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple={!single} className="sr-only" onChange={pick} />
          {busy ? 'Uploading…' : single ? (images.length ? 'Replace picture' : 'Upload picture') : '+ Add pictures'}
        </label>
      )}
      <p className="text-xs es-muted mt-1">JPG, PNG, WEBP or GIF, up to 10 MB each{single ? '' : `, ${max} per section`}.</p>
      {error && <p className="text-sm text-red-400 mt-1" role="alert">{error}</p>}
    </div>
  )
}

const FORMAT_HELP = 'Blank line = new paragraph. "- " starts a bullet, "## " a subheading, **bold**, [link text](https://…).'

/** Explorer admins edit the words on their site's home page. */
export default function ExplorerContentEditor() {
  usePageTitle('Edit Explorer Series site')
  const { content, loaded } = useSiteContent()
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [preview, setPreview] = useState(null) // section index

  useEffect(() => { if (loaded && !form) setForm(JSON.parse(JSON.stringify(content))) }, [loaded, content, form])

  if (!form) return <Spinner className="py-20" />

  const set = (key, value) => { setForm((f) => ({ ...f, [key]: value })); setMessage(null) }
  const setSection = (i, patch) => set('sections', form.sections.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  const moveSection = (i, by) => {
    const next = [...form.sections]
    const [item] = next.splice(i, 1)
    next.splice(i + by, 0, item)
    set('sections', next)
  }

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const saved = await saveSiteContent(form)
      setForm(saved)
      setMessage({ ok: true, text: 'Saved. The site shows your changes now.' })
    } catch (e) {
      setMessage({ ok: false, text: e.message || 'Could not save' })
    }
    setSaving(false)
  }

  return (
    <div className="space-y-5 max-w-3xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to={ES_PATHS.admin} className="text-sm es-link">← Admin</Link>
          <h1 className="es-heading text-3xl font-bold mt-1">Edit site content</h1>
          <p className="text-sm es-muted mt-1">These words appear on the Explorer Series home page. Standings, events and points come from the results you import.</p>
        </div>
        <Link to={ES_PATHS.home} className="es-btn-ghost text-sm" target="_blank">View the page ↗</Link>
      </div>

      <section className="es-card p-4 sm:p-5 space-y-4">
        <h2 className="es-heading text-xl font-bold">Top of the page</h2>
        <Field label="Announcement banner" hint="Optional. A short notice shown at the very top, e.g. a finale date. Leave blank to hide.">
          <textarea rows={2} className={inputCls} value={form.announcement} onChange={(e) => set('announcement', e.target.value)} />
        </Field>
        <Field label="Small line above the title" hint="Leave blank to show the current series name.">
          <input className={inputCls} value={form.kicker} onChange={(e) => set('kicker', e.target.value)} />
        </Field>
        <Field label="Title">
          <input className={inputCls} value={form.title} onChange={(e) => set('title', e.target.value)} />
        </Field>
        <Field label="Introduction" hint={FORMAT_HELP}>
          <textarea rows={4} className={inputCls} value={form.intro} onChange={(e) => set('intro', e.target.value)} />
        </Field>
        <div>
          <span className="block text-sm font-semibold mb-1">Picture beside the title</span>
          <span className="block text-xs es-muted mb-1.5">Leave empty to show the Explorer Series logo.</span>
          <div className="flex items-start gap-3">
            {!form.hero_image && <img src={ES_LOGO} alt="" className="w-28 rounded-md border border-[color:var(--es-rule)]" />}
            <PictureList single images={form.hero_image ? [form.hero_image] : []} onChange={(urls) => set('hero_image', urls[0] || '')} />
          </div>
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="Discord invite link" hint="Shows a Join our Discord button.">
            <input className={inputCls} placeholder="https://discord.gg/…" value={form.discord_url} onChange={(e) => set('discord_url', e.target.value)} />
          </Field>
          <Field label="Membership link" hint="Shows a Become a member button.">
            <input className={inputCls} placeholder="https://…" value={form.member_url} onChange={(e) => set('member_url', e.target.value)} />
          </Field>
        </div>
      </section>

      <section className="es-card p-4 sm:p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="es-heading text-xl font-bold">Sections</h2>
            <p className="text-xs es-muted">Your own blocks, shown under the standings: who's behind the Series, prizes, the finale, rules, FAQs.</p>
          </div>
          <button
            type="button"
            className="es-btn-ghost text-sm shrink-0"
            disabled={form.sections.length >= 20}
            onClick={() => set('sections', [...form.sections, { title: '', body: '', images: [], hidden: false }])}
          >
            + Add section
          </button>
        </div>
        {form.sections.length === 0 && <p className="text-sm es-muted">No sections yet.</p>}
        {form.sections.map((sec, i) => (
          <div key={i} className="rounded-lg border border-[color:var(--es-rule)] bg-[color:var(--es-card-2)] p-3 sm:p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs es-kicker">Section {i + 1}</span>
              <div className="ml-auto flex flex-wrap gap-1.5 text-sm">
                <button type="button" className="es-btn-ghost !px-2 !py-1" disabled={i === 0} onClick={() => moveSection(i, -1)} aria-label="Move up">↑</button>
                <button type="button" className="es-btn-ghost !px-2 !py-1" disabled={i === form.sections.length - 1} onClick={() => moveSection(i, 1)} aria-label="Move down">↓</button>
                <button type="button" className="es-btn-ghost !px-2 !py-1" onClick={() => setPreview(preview === i ? null : i)}>{preview === i ? 'Edit' : 'Preview'}</button>
                <label className="es-btn-ghost !px-2 !py-1 cursor-pointer">
                  <input type="checkbox" className="mr-1.5" checked={!!sec.hidden} onChange={(e) => setSection(i, { hidden: e.target.checked })} />
                  Hidden
                </label>
                <button
                  type="button"
                  className="es-btn-ghost !px-2 !py-1 text-red-400"
                  onClick={() => { if (window.confirm('Delete this section?')) set('sections', form.sections.filter((_, j) => j !== i)) }}
                >
                  Delete
                </button>
              </div>
            </div>
            {preview === i ? (
              <div className="es-card p-4">
                {sec.title && <h3 className="es-heading text-2xl font-bold mb-3">{sec.title}</h3>}
                <SiteText text={sec.body} />
                {sec.images?.length > 0 && (
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    {sec.images.map((src) => <img key={src} src={src} alt="" className="w-full aspect-[4/3] object-cover rounded" />)}
                  </div>
                )}
              </div>
            ) : (
              <>
                <Field label="Heading">
                  <input className={inputCls} value={sec.title} onChange={(e) => setSection(i, { title: e.target.value })} />
                </Field>
                <Field label="Text" hint={FORMAT_HELP}>
                  <textarea rows={6} className={inputCls} value={sec.body} onChange={(e) => setSection(i, { body: e.target.value })} />
                </Field>
                <div>
                  <span className="block text-sm font-semibold mb-1">Pictures</span>
                  <span className="block text-xs es-muted mb-1.5">One picture sits beside the text; more make a gallery.</span>
                  <PictureList images={sec.images || []} onChange={(urls) => setSection(i, { images: urls })} />
                </div>
              </>
            )}
          </div>
        ))}
      </section>

      <section className="es-card p-4 sm:p-5 space-y-4">
        <h2 className="es-heading text-xl font-bold">Bottom of the page</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.show_points_guide !== false} onChange={(e) => set('show_points_guide', e.target.checked)} />
          Show "How Series points work" (built from the current series' points settings)
        </label>
        <Field label="Host call-out heading">
          <input className={inputCls} value={form.host_title} onChange={(e) => set('host_title', e.target.value)} />
        </Field>
        <Field label="Host call-out text">
          <textarea rows={2} className={inputCls} value={form.host_text} onChange={(e) => set('host_text', e.target.value)} />
        </Field>
      </section>

      <div className="sticky bottom-3 es-card px-4 py-3 flex flex-wrap items-center gap-3 justify-between">
        {message ? (
          <span className={`text-sm ${message.ok ? 'text-accent-green' : 'text-red-400'}`} role="status">{message.text}</span>
        ) : <span className="text-sm es-muted">Changes go live as soon as you save.</span>}
        <button type="button" className="es-btn" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
      </div>
    </div>
  )
}
