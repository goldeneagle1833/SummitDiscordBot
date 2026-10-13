import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  adminBuildMetaReport,
  adminDeleteMetaReport,
  adminGetMetaReport,
  adminListMetaReports,
  adminPublishMetaReport,
  adminSaveMetaReportNotes,
  adminSaveMetaReportStory,
  adminUnpublishMetaReport,
} from '@/api/metaReports'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

/**
 * Admin: Meta Reports.
 *
 * Reports build and publish themselves on the 1st and 16th (once PSO has
 * released the period's card data). This page is for everything else:
 * building past periods, editing the takeaways, and publishing by hand, with
 * or without the Discord post, home page banner and email.
 */

const panel = 'bg-bg-surface border border-border rounded-lg p-4'
const btn = 'text-sm px-3 py-1.5 rounded border border-border hover:border-secondary disabled:opacity-50'
const goldBtn = 'text-sm px-3 py-1.5 rounded bg-secondary hover:bg-secondary/80 text-black font-medium disabled:opacity-50'

function StatusPill({ report }) {
  const published = report.status === 'published'
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${published ? 'border-green-500/60 text-green-400' : 'border-border text-text-muted'}`}>
      {published ? 'Published' : 'Draft'}
    </span>
  )
}

function Delivery({ report, emailConfigured }) {
  if (report.status !== 'published') return null
  if (!report.announce) return <span className="text-xs text-text-muted">Published quietly</span>
  const e = report.emails || {}
  const parts = [
    report.discordPostedAt ? 'Discord ✓' : 'Discord pending',
    report.bannerCreatedAt ? 'Banner ✓' : 'Banner pending',
    report.dmsSentAt ? 'DMs ✓' : 'DMs pending',
  ]
  if (emailConfigured || e.sent) {
    parts.push(`Emails ${e.sent || 0} sent${e.pending ? `, ${e.pending} queued` : ''}${e.failed ? `, ${e.failed} failed` : ''}`)
  }
  return <span className="text-xs text-text-muted">{parts.join(' · ')}</span>
}

function StoryEditor({ slug, onSaved }) {
  const [story, setStory] = useState(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    adminGetMetaReport(slug).then((r) => setStory(r.story || []))
  }, [slug])

  if (!story) return <Spinner className="py-4" />

  const update = (i, key, value) => setStory(story.map((s, j) => (j === i ? { ...s, [key]: value } : s)))
  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      const res = await adminSaveMetaReportStory(slug, story)
      setStory(res.story)
      setMsg('Saved')
      onSaved?.()
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-3 mt-3">
      {story.map((s, i) => (
        <div key={i} className="grid gap-1.5">
          <label className="text-xs text-text-muted" htmlFor={`headline-${slug}-${i}`}>Takeaway {i + 1}</label>
          <input id={`headline-${slug}-${i}`} value={s.headline} onChange={(e) => update(i, 'headline', e.target.value)}
                 className="bg-bg-dark border border-border rounded px-3 py-2 text-sm" placeholder="Headline" />
          <input value={s.detail} onChange={(e) => update(i, 'detail', e.target.value)} aria-label={`Takeaway ${i + 1} detail`}
                 className="bg-bg-dark border border-border rounded px-3 py-2 text-sm" placeholder="Supporting number" />
          <button type="button" className="text-xs text-accent-red justify-self-start"
                  onClick={() => setStory(story.filter((_, j) => j !== i))}>Remove</button>
        </div>
      ))}
      <div className="flex gap-2 items-center flex-wrap">
        {story.length < 6 && (
          <button type="button" className={btn} onClick={() => setStory([...story, { headline: '', detail: '' }])}>Add takeaway</button>
        )}
        <button type="button" className={goldBtn} onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save takeaways'}</button>
        {msg && <span className="text-sm text-text-muted">{msg}</span>}
      </div>
    </div>
  )
}

function CounterNotes({ slug }) {
  const [picks, setPicks] = useState(null)
  const [notes, setNotes] = useState({})
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    adminGetMetaReport(slug).then((r) => {
      setPicks(r.payload?.ranked?.counters || [])
      setNotes(r.notes?.counters || {})
    })
  }, [slug])

  if (!picks) return <Spinner className="py-4" />
  if (!picks.length) return <p className="text-sm text-text-muted mt-3">No counter picks in this report.</p>

  const save = async () => {
    setSaving(true)
    setMsg('')
    try {
      const res = await adminSaveMetaReportNotes(slug, notes)
      setNotes(res.counters)
      setMsg('Saved')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-3 mt-3">
      <p className="text-xs text-text-muted">Leave a box empty to use the automatic explanation shown under it.</p>
      {picks.map((p) => (
        <div key={p.target} className="grid gap-1">
          <label className="text-xs text-text-muted" htmlFor={`why-${slug}-${p.target}`}>Why play {p.counter} into {p.target}</label>
          <input id={`why-${slug}-${p.target}`} value={notes[p.target] || ''} maxLength={300}
                 onChange={(e) => setNotes({ ...notes, [p.target]: e.target.value })}
                 className="bg-bg-dark border border-border rounded px-3 py-2 text-sm" placeholder={p.why || 'Your explanation'} />
          {p.why && <span className="text-xs text-text-muted">Automatic: {p.why}</span>}
        </div>
      ))}
      <div className="flex gap-2 items-center">
        <button type="button" className={goldBtn} onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save counter notes'}</button>
        {msg && <span className="text-sm text-text-muted">{msg}</span>}
      </div>
    </div>
  )
}

export default function MetaReportsAdmin() {
  usePageTitle('Meta Reports')
  const [data, setData] = useState(null)
  const [period, setPeriod] = useState('')
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)

  const load = useCallback(() => adminListMetaReports()
    .then((res) => {
      setData(res)
      setPeriod((p) => p || res.periods?.[0]?.slug || '')
    })
    .catch((err) => setError(err.message)), [])

  useEffect(() => { load() }, [load])

  const run = async (key, fn) => {
    setBusy(key)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  if (!data) return error ? <p className="text-accent-red">{error}</p> : <Spinner className="py-20" />

  const subs = data.subscribers || {}

  return (
    <div className="max-w-4xl mx-auto grid gap-6">
      <header>
        <h1 className="font-display text-secondary text-3xl">Meta Reports</h1>
        <p className="text-sm text-text-muted mt-1">
          Reports publish themselves on the 1st and 16th. Next up: <b className="text-text-primary">{data.next?.label}</b>, due {data.next?.publishLabel}.
          Publishing posts to the content channel, puts a banner on the home page and DMs players who turned report DMs on.
        </p>
      </header>

      <div className={`${panel} flex flex-wrap gap-6 text-sm`}>
        <span><b className="text-lg">{data.dmSubscribers || 0}</b> players get report DMs on Discord</span>
        {data.emailConfigured && (
          <>
            <span><b className="text-lg">{subs.active || 0}</b> email subscribers</span>
            <span className="text-text-muted">{subs.unconfirmed || 0} waiting to confirm</span>
          </>
        )}
      </div>

      <div className={`${panel} flex flex-wrap gap-3 items-end`}>
        <div>
          <label htmlFor="build-period" className="block text-xs text-text-muted mb-1">Build or refresh a report</label>
          <select id="build-period" value={period} onChange={(e) => setPeriod(e.target.value)}
                  className="bg-bg-dark border border-border rounded px-3 py-2 text-sm">
            {data.periods.map((p) => <option key={p.slug} value={p.slug}>{`${p.label} (due ${p.publishLabel})`}</option>)}
          </select>
        </div>
        <button type="button" className={goldBtn} disabled={!period || busy}
                onClick={() => run('build', () => adminBuildMetaReport(period))}>
          {busy === 'build' ? 'Building…' : 'Build'}
        </button>
        <p className="text-xs text-text-muted w-full">Building never publishes. Refreshing a report updates its numbers and keeps any takeaways you edited.</p>
      </div>

      {error && <p className="text-accent-red text-sm" role="alert">{error}</p>}

      <div className="grid gap-3">
        {data.reports.length === 0 && <p className="text-text-muted text-sm">No reports yet.</p>}
        {data.reports.map((r) => (
          <div key={r.slug} className={panel}>
            <div className="flex flex-wrap gap-2 items-center justify-between">
              <div className="min-w-0">
                <div className="flex gap-2 items-center flex-wrap">
                  <b>{r.label}</b> <StatusPill report={r} />
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  Due {r.publishLabel} · built {r.builtAt} UTC{r.publishedAt ? ` · published ${r.publishedAt} UTC by ${r.publishedBy}` : ''}
                </div>
                <Delivery report={r} emailConfigured={data.emailConfigured} />
              </div>
              <div className="flex flex-wrap gap-2">
                {r.status === 'published' && <Link to={`/meta-report/${r.slug}`} className={btn}>View</Link>}
                <button type="button" className={btn} onClick={() => setEditing(editing === r.slug ? null : r.slug)}>
                  {editing === r.slug ? 'Close' : 'Edit takeaways'}
                </button>
                <button type="button" className={btn} onClick={() => setEditing(editing === `${r.slug}:why` ? null : `${r.slug}:why`)}>
                  {editing === `${r.slug}:why` ? 'Close' : 'Edit counter notes'}
                </button>
                {r.status === 'draft' ? (
                  <>
                    <button type="button" className={goldBtn} disabled={!!busy}
                            onClick={() => run(r.slug, () => adminPublishMetaReport(r.slug, true))}>Publish and announce</button>
                    <button type="button" className={btn} disabled={!!busy}
                            onClick={() => run(r.slug, () => adminPublishMetaReport(r.slug, false))}>Publish quietly</button>
                    <button type="button" className={`${btn} text-accent-red`} disabled={!!busy}
                            onClick={() => run(r.slug, () => adminDeleteMetaReport(r.slug))}>Delete</button>
                  </>
                ) : (
                  <button type="button" className={btn} disabled={!!busy}
                          onClick={() => run(r.slug, () => adminUnpublishMetaReport(r.slug))}>Unpublish</button>
                )}
              </div>
            </div>
            {editing === r.slug && <StoryEditor slug={r.slug} onSaved={load} />}
            {editing === `${r.slug}:why` && <CounterNotes slug={r.slug} />}
          </div>
        ))}
      </div>
    </div>
  )
}
