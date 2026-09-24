import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import {
  getApplications,
  getApplication,
  voteOnApplication,
  setApplicationStatus,
  addApplicationComment,
  getPublishPreview,
  publishDecisions,
  addCandidate,
  deleteApplication,
  regeocodeApplication,
  refreshLgsAttendance,
  EXPORT_CSV_URL,
} from '@/api/explorerApplications'

// Leaflet pulls in a sizeable bundle and needs a real DOM, so keep it out of
// the main chunk.
const ApplicationsMap = lazy(() => import('@/components/explorer/ApplicationsMap'))
import EventsMapToggle from '@/components/explorer/EventsMapToggle'
import LgsAttendance from '@/components/explorer/LgsAttendance'

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'pre_approved', label: 'Pre-approved' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

const STATUS_STYLES = {
  pending: 'bg-amber-400/15 text-amber-300 border-amber-400/30',
  pre_approved: 'bg-blue-400/15 text-blue-300 border-blue-400/30',
  approved: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30',
  rejected: 'bg-red-400/15 text-red-300 border-red-400/30',
}

const CRITERIA = [
  { key: 'enthusiasm', label: 'Enthusiasm' },
  { key: 'track_record', label: 'Track record' },
  { key: 'local_activity', label: 'Local activity' },
]

const inputClass =
  'w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary' +
  ' focus:outline-none focus:border-primary/60 placeholder:text-text-muted'

function statusLabel(status) {
  return STATUS_OPTIONS.find((o) => o.value === status)?.label || status
}

const DECIDED = ['approved', 'rejected']

// Status changes stay with the Council until someone publishes them.
function isUnpublished(application) {
  const published = application.published_status || null
  return DECIDED.includes(application.status)
    ? published !== application.status
    : published !== null
}

const CONFIRM_WORD = 'publish'

function PublishModal({ preview, onClose, onPublished }) {
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const confirmed = typed.trim().toLowerCase() === CONFIRM_WORD

  const submit = async (e) => {
    e.preventDefault()
    if (!confirmed) return
    setBusy(true)
    setError(null)
    try {
      const data = await publishDecisions(typed.trim())
      onPublished(data.published)
    } catch (err) {
      setError(err.message || 'Publishing failed')
      setBusy(false)
    }
  }

  const messaged = preview.approved + preview.rejected - preview.no_account

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <form
        role="dialog"
        aria-label="Publish decisions"
        onSubmit={submit}
        className="bg-bg-base border border-border rounded-lg w-full max-w-md p-5 space-y-4"
      >
        <h2 className="text-lg font-display text-secondary">Publish decisions</h2>
        <div className="text-sm text-text-muted space-y-2">
          <p>
            Each applicant will see their decision on their application page and get a
            Discord DM and a site notification.
          </p>
          <ul className="list-disc pl-5 text-text-primary">
            <li>{preview.approved} approved</li>
            <li>{preview.rejected} rejected</li>
            {preview.withdrawn > 0 && (
              <li>
                {preview.withdrawn} earlier decision{preview.withdrawn === 1 ? '' : 's'} moved
                back to review (hidden again, no message sent)
              </li>
            )}
          </ul>
          {preview.no_account > 0 && (
            <p>
              {preview.no_account} of these {preview.no_account === 1 ? 'is a candidate' : 'are candidates'}{' '}
              added by an admin, with no account to message.
            </p>
          )}
          <p>
            {messaged} applicant{messaged === 1 ? '' : 's'} will be messaged. This can&apos;t be undone.
          </p>
        </div>
        <label className="block space-y-1">
          <span className="block text-sm text-text-primary">
            Type <span className="font-mono text-secondary">{CONFIRM_WORD}</span> to confirm
          </span>
          <input
            autoFocus
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-label="Type publish to confirm"
            className={inputClass}
          />
        </label>
        {error && <p className="text-xs text-accent-red">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="px-4 py-2 text-sm bg-bg-elevated border border-border rounded hover:border-secondary disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!confirmed || busy}
            className="px-4 py-2 text-sm bg-secondary text-black font-medium rounded hover:opacity-90 disabled:opacity-40"
          >
            {busy ? 'Publishing…' : 'Publish'}
          </button>
        </div>
      </form>
    </div>
  )
}

function ScoreSelect({ value, onChange, label }) {
  return (
    <label className="flex items-center justify-between gap-3 text-sm">
      <span className="text-text-muted">{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        aria-label={label}
        className="bg-bg-surface border border-border rounded px-2 py-1 text-sm"
      >
        <option value="">—</option>
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
    </label>
  )
}

function ApplicationCard({ application, onOpen }) {
  const name = [application.first_name, application.last_name].filter(Boolean).join(' ')
  const place = [application.city, application.state].filter(Boolean).join(', ')

  return (
    <button
      onClick={() => onOpen(application)}
      className="text-left bg-bg-raised border border-border rounded-lg p-4 hover:border-secondary transition-colors space-y-2"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-text-primary font-medium">{name || application.discord_handle || 'Unnamed'}</div>
          {application.discord_handle && (
            <div className="text-xs text-text-muted">{application.discord_handle}</div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`text-xs px-2 py-0.5 rounded border ${STATUS_STYLES[application.status] || ''}`}>
            {statusLabel(application.status)}
          </span>
          {isUnpublished(application) && (
            <span className="text-[11px] text-amber-400">Not published</span>
          )}
        </div>
      </div>

      <div className="text-sm text-text-muted">{place || 'Location unknown'}</div>
      {application.lgs_name && (
        <div className="text-xs text-text-muted truncate">{application.lgs_name}</div>
      )}

      <div className="flex items-center justify-between text-xs pt-1">
        <span className="text-text-muted">
          {application.vote_count || 0} vote{application.vote_count === 1 ? '' : 's'}
          {application.comment_count ? ` · ${application.comment_count} note${application.comment_count === 1 ? '' : 's'}` : ''}
        </span>
        <span className="text-secondary font-medium">
          {application.average_score != null ? `${application.average_score} / 5` : 'Unscored'}
        </span>
      </div>

      {application.source === 'admin_added' && (
        <div className="text-xs text-text-muted italic">Added by {application.created_by || 'an admin'}</div>
      )}
      {application.latitude == null && (
        <div className="text-xs text-amber-400">Not on the map</div>
      )}
    </button>
  )
}

function DetailRow({ label, value }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-1 py-2 border-b border-border/50">
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className="sm:col-span-2 text-sm text-text-primary whitespace-pre-wrap break-words">
        {value}
      </dd>
    </div>
  )
}

function ApplicationDetail({ applicationId, currentUserId, onClose, onChanged }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [scores, setScores] = useState({ enthusiasm: null, track_record: null, local_activity: null })
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getApplication(applicationId)
      setDetail(data)
      const mine = (data.votes || []).find((v) => String(v.voter_user_id) === String(currentUserId))
      setScores({
        enthusiasm: mine?.enthusiasm ?? null,
        track_record: mine?.track_record ?? null,
        local_activity: mine?.local_activity ?? null,
      })
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to load application')
    }
    setLoading(false)
  }, [applicationId, currentUserId])

  useEffect(() => { load() }, [load])

  const run = async (action) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      await load()
      onChanged?.()
    } catch (err) {
      setError(err.message || 'Request failed')
    }
    setBusy(false)
  }

  const application = detail?.application

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4">
      <div
        role="dialog"
        aria-label="Application detail"
        className="bg-bg-base border border-border rounded-lg w-full max-w-3xl my-8"
      >
        <div className="flex items-center justify-between gap-3 p-4 border-b border-border">
          <h2 className="text-lg font-display text-secondary">
            {loading
              ? 'Loading…'
              : [application?.first_name, application?.last_name].filter(Boolean).join(' ')
                || application?.discord_handle
                || 'Application'}
          </h2>
          <button onClick={onClose} className="text-sm text-text-muted hover:text-text-primary">
            Close
          </button>
        </div>

        <div className="p-4 space-y-5">
          {error && (
            <div className="text-sm rounded p-3 border bg-accent-red/10 border-accent-red/30 text-accent-red">
              {error}
            </div>
          )}

          {application && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {STATUS_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    disabled={busy}
                    onClick={() => run(() => setApplicationStatus(application.id, option.value))}
                    className={`text-xs px-3 py-1 rounded border transition-colors disabled:opacity-40 ${
                      application.status === option.value
                        ? STATUS_STYLES[option.value]
                        : 'border-border text-text-muted hover:border-secondary'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
                {application.latitude == null && (
                  <button
                    disabled={busy}
                    onClick={() => run(() => regeocodeApplication(application.id))}
                    className="text-xs px-3 py-1 rounded border border-border text-text-muted hover:border-secondary disabled:opacity-40"
                  >
                    Find on map
                  </button>
                )}
              </div>

              <dl>
                <DetailRow label="Discord handle" value={application.discord_handle} />
                <DetailRow label="Email" value={application.email} />
                <DetailRow
                  label="Location"
                  value={[application.city, application.state, application.country]
                    .filter(Boolean).join(', ')}
                />
                <DetailRow label="Local game store" value={application.lgs_name} />
                <DetailRow label="Store on sorcerytcg.com" value={application.lgs_url} />
                <DetailRow label="Owner confirmed?" value={application.lgs_confirmed} />
                <DetailRow label="Expected attendance" value={application.expected_attendance} />
                <DetailRow label="Proposed dates" value={application.proposed_dates} />
                <DetailRow label="Events run" value={application.events_run_count} />
                <DetailRow label="Average headcount" value={application.avg_headcount} />
                <DetailRow label="Event experience" value={application.events_run} />
                <DetailRow label="Why they want to host" value={application.motivation} />
                <DetailRow label="Reference" value={application.reference_contact} />
                <DetailRow label="Anything else" value={application.anything_else} />
                <DetailRow label="Other TOs to contact" value={application.referral} />
                <DetailRow label="Submitted" value={application.submitted_at} />
              </dl>

              <LgsAttendance
                application={application}
                refreshing={busy}
                onRefresh={() => run(() => refreshLgsAttendance(application.id))}
              />

              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-text-primary">Your scores</h3>
                <div className="bg-bg-raised border border-border rounded-lg p-4 space-y-2">
                  {CRITERIA.map(({ key, label }) => (
                    <ScoreSelect
                      key={key}
                      label={label}
                      value={scores[key]}
                      onChange={(value) => setScores((s) => ({ ...s, [key]: value }))}
                    />
                  ))}
                  <button
                    disabled={busy}
                    onClick={() => run(() => voteOnApplication(application.id, scores))}
                    className="mt-2 px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
                  >
                    Save scores
                  </button>
                </div>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold text-text-primary">
                  All reviewers ({detail.votes.length})
                </h3>
                {detail.votes.length === 0 ? (
                  <p className="text-sm text-text-muted">No scores yet.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-text-muted border-b border-border">
                        <th className="py-1 font-normal">Reviewer</th>
                        {CRITERIA.map((c) => (
                          <th key={c.key} className="py-1 font-normal">{c.label}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detail.votes.map((vote) => (
                        <tr key={vote.id} className="border-b border-border/50">
                          <td className="py-1">{vote.voter_name || vote.voter_user_id}</td>
                          {CRITERIA.map((c) => (
                            <td key={c.key} className="py-1">{vote[c.key] ?? '—'}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold text-text-primary">
                  Notes ({detail.comments.length})
                </h3>
                {detail.comments.map((c) => (
                  <div key={c.id} className="bg-bg-raised border border-border rounded p-3">
                    <div className="text-xs text-text-muted">
                      {c.author_name || c.author_user_id} · {c.created_at}
                    </div>
                    <p className="text-sm text-text-primary whitespace-pre-wrap">{c.body}</p>
                  </div>
                ))}
                <textarea
                  rows={3}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="Add a note for the other Explorer admins..."
                  aria-label="Add a note"
                  className={inputClass}
                />
                <button
                  disabled={busy || !comment.trim()}
                  onClick={() => run(async () => {
                    await addApplicationComment(application.id, comment.trim())
                    setComment('')
                  })}
                  className="px-4 py-2 text-sm bg-bg-elevated border border-border rounded hover:border-secondary disabled:opacity-40"
                >
                  Add note
                </button>
              </section>

              <div className="pt-2 border-t border-border">
                <button
                  disabled={busy}
                  onClick={() => {
                    if (!confirm('Delete this application permanently?')) return
                    run(async () => {
                      await deleteApplication(application.id)
                      onClose()
                    })
                  }}
                  className="text-xs text-accent-red hover:underline disabled:opacity-40"
                >
                  Delete application
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function AddCandidateForm({ onAdded }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    discord_handle: '', first_name: '', last_name: '', city: '', state: '', country: '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const update = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await addCandidate(form)
      setForm({ discord_handle: '', first_name: '', last_name: '', city: '', state: '', country: '' })
      setOpen(false)
      onAdded?.()
    } catch (err) {
      setError(err.message || 'Request failed')
    }
    setBusy(false)
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary text-text-primary transition-colors"
      >
        + Add Candidate
      </button>
    )
  }

  return (
    <form onSubmit={submit} className="w-full bg-bg-raised border border-border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Add a candidate</h3>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-text-muted hover:text-text-primary">
          Cancel
        </button>
      </div>
      <p className="text-xs text-text-muted">
        For prospective Navigators who haven&apos;t applied yet. They can still submit a real
        application later.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <input value={form.discord_handle} onChange={update('discord_handle')} placeholder="Discord handle" aria-label="Discord handle" className={inputClass} />
        <input value={form.first_name} onChange={update('first_name')} placeholder="First name" aria-label="First name" className={inputClass} />
        <input value={form.last_name} onChange={update('last_name')} placeholder="Last name" aria-label="Last name" className={inputClass} />
        <input value={form.city} onChange={update('city')} placeholder="City" aria-label="City" className={inputClass} />
        <input value={form.state} onChange={update('state')} placeholder="State" aria-label="State" className={inputClass} />
        <input value={form.country} onChange={update('country')} placeholder="Country" aria-label="Country" className={inputClass} />
      </div>
      {error && <p className="text-xs text-accent-red">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="px-4 py-2 text-sm bg-secondary text-black rounded hover:opacity-90 disabled:opacity-40"
      >
        {busy ? 'Adding…' : 'Add Candidate'}
      </button>
    </form>
  )
}

export default function ExplorerApplications() {
  usePageTitle('Explorer Applications')

  const { user } = useAuth()
  const [applications, setApplications] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [preview, setPreview] = useState(null)
  const [publishOpen, setPublishOpen] = useState(false)
  const [publishResult, setPublishResult] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getApplications(statusFilter || undefined)
      setApplications(data.applications || [])
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to load applications')
      setApplications([])
    }
    setLoading(false)
    // Counted across every status, whatever the filter shows.
    getPublishPreview()
      .then((data) => setPreview(data.pending))
      .catch(() => setPreview(null))
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  const unmapped = applications.filter((a) => a.latitude == null).length

  return (
    <div className="max-w-content mx-auto px-4 py-8 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display text-secondary">Explorer Applications</h1>
          <p className="text-sm text-text-muted">
            Review, score and approve applications to host Explorer Series events.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter by status"
            className="bg-bg-surface border border-border rounded px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <a
            href={EXPORT_CSV_URL}
            className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary text-text-primary transition-colors"
          >
            Export CSV
          </a>
          <AddCandidateForm onAdded={load} />
          <button
            onClick={() => { setPublishResult(null); setPublishOpen(true) }}
            disabled={!preview || preview.total === 0}
            title={preview?.total === 0 ? 'No new decisions to publish' : undefined}
            className="px-3 py-1.5 text-sm bg-secondary text-black font-medium rounded hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            Publish{preview?.total ? ` (${preview.total})` : ''}
          </button>
        </div>
      </div>

      {publishResult && (
        <div
          role="status"
          className="text-sm rounded p-3 border bg-accent-green/10 border-accent-green/30 text-accent-green"
        >
          Published {publishResult.approved + publishResult.rejected} decision
          {publishResult.approved + publishResult.rejected === 1 ? '' : 's'}.{' '}
          {publishResult.dms_queued} Discord DM{publishResult.dms_queued === 1 ? '' : 's'} queued;
          the bot sends them within a minute.
        </div>
      )}

      {error && (
        <div className="text-sm rounded p-3 border bg-accent-red/10 border-accent-red/30 text-accent-red">
          {error}
        </div>
      )}

      <EventsMapToggle />

      <Suspense fallback={<div className="h-80 rounded-lg border border-border bg-bg-raised" />}>
        <ApplicationsMap
          applications={applications}
          onSelect={(application) => setSelectedId(application.id)}
        />
      </Suspense>
      {unmapped > 0 && (
        <p className="text-xs text-text-muted">
          {unmapped} application{unmapped === 1 ? '' : 's'} could not be placed on the map.
          Open one and use &ldquo;Find on map&rdquo; to retry.
        </p>
      )}

      {loading ? (
        <p className="text-sm text-text-muted">Loading applications…</p>
      ) : applications.length === 0 ? (
        <p className="text-sm text-text-muted">No applications yet.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {applications.map((application) => (
            <ApplicationCard
              key={application.id}
              application={application}
              onOpen={() => setSelectedId(application.id)}
            />
          ))}
        </div>
      )}

      {publishOpen && preview && (
        <PublishModal
          preview={preview}
          onClose={() => setPublishOpen(false)}
          onPublished={(result) => {
            setPublishOpen(false)
            setPublishResult(result)
            load()
          }}
        />
      )}

      {selectedId && (
        <ApplicationDetail
          applicationId={selectedId}
          currentUserId={user?.id}
          onClose={() => setSelectedId(null)}
          onChanged={load}
        />
      )}
    </div>
  )
}
