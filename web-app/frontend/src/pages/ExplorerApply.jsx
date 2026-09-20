import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import {
  submitApplication,
  getMyApplication,
  updateMyApplication,
} from '@/api/explorerApplications'

const NAVIGATOR_INFO_URL = 'https://jamesboo.com/explorer-series-2027-application'

const EXPLORER_DISCORD_INVITE = 'https://discord.gg/GrxsArdzr'

const ATTENDANCE_OPTIONS = [
  'Fewer than 8',
  '8-16',
  '17-24',
  '25-32',
  '33-48',
  'More than 48',
]

const STATUS_LABELS = {
  pending: 'Under review',
  pre_approved: 'Pre-approved',
  approved: 'Approved',
  rejected: 'Not accepted',
}

// The control is nested inside the <label> so it is implicitly associated with
// it — no id plumbing, and screen readers announce the label correctly.
function Field({ label, hint, children, required }) {
  return (
    <label className="block space-y-1">
      <span className="block text-sm text-text-primary">
        {label} {required && <span className="text-accent-red">*</span>}
      </span>
      {hint && <span className="block text-xs text-text-muted">{hint}</span>}
      {children}
    </label>
  )
}

const inputClass =
  'w-full bg-bg-surface border border-border rounded px-3 py-2 text-sm text-text-primary' +
  ' focus:outline-none focus:border-primary/60 placeholder:text-text-muted'

export default function ExplorerApply() {
  usePageTitle('Apply to Host an Explorer Event')

  const { user, loading } = useAuth()
  const [existing, setExisting] = useState(null)
  const [checking, setChecking] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)
  const [saved, setSaved] = useState(false)
  // Once the Council decides, the answers become the record of that decision.
  const EDITABLE = ['pending', 'pre_approved']

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    discord_handle: '',
    city: '',
    state: '',
    country: 'USA',
    lgs_name: '',
    lgs_url: '',
    lgs_confirmed: 'No',
    expected_attendance: ATTENDANCE_OPTIONS[3],
    proposed_dates: '',
    events_run_count: '',
    events_run: '',
    avg_headcount: '',
    motivation: '',
    read_navigator_role: false,
    reference_contact: '',
    anything_else: '',
    referral: '',
  })

  useEffect(() => {
    if (!user) {
      setChecking(false)
      return
    }
    getMyApplication()
      .then((data) => setExisting(data.application))
      .catch(() => setExisting(null))
      .finally(() => setChecking(false))
  }, [user])

  useEffect(() => {
    // Only a Discord login tells us their real handle; Google users type it.
    if (user?.username && user?.auth_provider === 'discord') {
      setForm((f) => (f.discord_handle ? f : { ...f, discord_handle: user.username }))
    }
  }, [user])

  // Load their existing answers in so they can correct them.
  useEffect(() => {
    if (!existing) return
    setForm((f) => {
      const filled = { ...f }
      Object.keys(f).forEach((key) => {
        const value = existing[key]
        if (value === null || value === undefined) return
        filled[key] = key === 'read_navigator_role' ? Boolean(value) : value
      })
      return filled
    })
  }, [existing])

  const update = (name) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [name]: value }))
  }

  const editing = Boolean(existing) && EDITABLE.includes(existing.status)
  const decided = Boolean(existing) && !EDITABLE.includes(existing.status)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setSaved(false)
    try {
      if (editing) {
        const data = await updateMyApplication(form)
        setExisting(data.application)
        setSaved(true)
        window.scrollTo({ top: 0, behavior: 'smooth' })
      } else {
        await submitApplication(form)
        setSubmitted(true)
      }
    } catch (err) {
      setError(err.message || 'Something went wrong submitting your application.')
    }
    setSubmitting(false)
  }

  if (loading || checking) {
    return (
      <div className="max-w-content mx-auto px-4 py-8">
        <p className="text-sm text-text-muted">Loading…</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="max-w-content mx-auto px-4 py-8 space-y-4">
        <h1 className="text-2xl font-display text-text-primary">
          Apply to Host an Explorer Event
        </h1>
        <p className="text-sm text-text-muted">
          Please log in with Discord to apply. We use your Discord account so the Explorer
          Series council can reach you about your application.
        </p>
        <Link
          to={`/login?next=${encodeURIComponent('/explorer/apply')}`}
          className="inline-block px-4 py-2 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 transition-colors"
        >
          Log in with Discord
        </Link>
      </div>
    )
  }

  if (submitted || decided) {
    const status = existing?.status || 'pending'
    return (
      <div className="max-w-content mx-auto px-4 py-8 space-y-4">
        <h1 className="text-2xl font-display text-text-primary">
          Apply to Host an Explorer Event
        </h1>
        <div className="bg-bg-surface border border-border rounded-lg p-6 space-y-2">
          <p className="text-text-primary font-medium">
            {submitted ? 'Thanks — your application is in.' : 'Your application has been reviewed.'}
          </p>
          <p className="text-sm text-text-muted">
            Status: <span className="text-text-primary">{STATUS_LABELS[status] || status}</span>
          </p>
          <p className="text-sm text-text-muted">
            The Explorer Series Council reviews applications in batches and will get back to
            you in late November. If you need to change anything, join the{' '}
            <a
              href={EXPLORER_DISCORD_INVITE}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              Explorer Series Discord server
            </a>{' '}
            and ask for help in our #questions channel.
          </p>
          <div className="flex flex-wrap items-center gap-4 pt-1">
            {submitted && (
              <button
                onClick={() => { setSubmitted(false); setSaved(false) }}
                className="text-sm text-primary hover:underline"
              >
                Edit your application
              </button>
            )}
            <Link to="/explorer" className="text-sm text-primary hover:underline">
              Back to the Community Series
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-content mx-auto px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-display text-text-primary">
          Apply to Host an Explorer Event
        </h1>
        <p className="text-sm text-text-muted mt-1 max-w-3xl">
          The Sorcery Explorer Series is a player-run annual circuit. Hosts (&ldquo;Navigators&rdquo;)
          run an event at their local game store. {editing ? 'For reference, see' : 'Before applying, please read'} the{' '}
          <a
            href={NAVIGATOR_INFO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Navigator role summary and FAQs
          </a>
          .
        </p>
      </div>

      {editing && (
        <div className="mb-6 bg-bg-surface border border-border rounded-lg p-4 space-y-1">
          <p className="text-sm text-text-primary font-medium">
            You have already applied — status:{' '}
            {STATUS_LABELS[existing.status] || existing.status}
          </p>
          <p className="text-xs text-text-muted">
            You can change your answers below until the Council makes a decision.
          </p>
        </div>
      )}

      {saved && (
        <div
          role="status"
          className="mb-6 text-sm rounded p-3 border bg-accent-green/10 border-accent-green/30 text-accent-green"
        >
          Your application has been updated.
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">About you</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="First name" required>
              <input required value={form.first_name} onChange={update('first_name')} className={inputClass} />
            </Field>
            <Field label="Last name" required>
              <input required value={form.last_name} onChange={update('last_name')} className={inputClass} />
            </Field>
            <Field label="Email address" required>
              <input required type="email" value={form.email} onChange={update('email')} className={inputClass} />
            </Field>
            <Field label="Discord handle">
              <input value={form.discord_handle} onChange={update('discord_handle')} className={inputClass} />
            </Field>
          </div>
        </section>

        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">Where you play</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="City or town" hint="Just one, where you play Sorcery locally" required>
              <input required value={form.city} onChange={update('city')} className={inputClass} />
            </Field>
            <Field label="State or province" required>
              <input required value={form.state} onChange={update('state')} className={inputClass} />
            </Field>
            <Field label="Country">
              <input value={form.country} onChange={update('country')} className={inputClass} />
            </Field>
          </div>
        </section>

        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">Your local game store</h2>
          <Field label="Name of the LGS where you wish to host" hint="Just one, please" required>
            <input required value={form.lgs_name} onChange={update('lgs_name')} className={inputClass} />
          </Field>
          <Field
            label="LGS page on SorceryTCG.com"
            hint={'Paste their store URL. If they are not registered, type "not registered".'}
          >
            <input value={form.lgs_url} onChange={update('lgs_url')} className={inputClass} />
          </Field>
          <Field label="Has the LGS owner already confirmed they'd like to host this with you?">
            <select value={form.lgs_confirmed} onChange={update('lgs_confirmed')} className={inputClass}>
              <option value="Yes">Yes</option>
              <option value="No">No</option>
              <option value="In discussion">In discussion</option>
            </select>
          </Field>
        </section>

        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">The event</h2>
          <Field
            label="Roughly how many local players would you expect to attend?"
            hint="Based on prior attendance"
          >
            <select value={form.expected_attendance} onChange={update('expected_attendance')} className={inputClass}>
              {ATTENDANCE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </Field>
          <Field
            label="Three potential dates you'd like to host"
            hint="Rough ideas are fine for now"
          >
            <input
              value={form.proposed_dates}
              onChange={update('proposed_dates')}
              placeholder="e.g. 3/6/27, 4/10/27, 6/12/27"
              className={inputClass}
            />
          </Field>
        </section>

        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">Your experience</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="How many local events have you run?">
              <input
                type="number"
                min="0"
                value={form.events_run_count}
                onChange={update('events_run_count')}
                className={inputClass}
              />
            </Field>
            <Field label="Rough average headcount at those events">
              <input value={form.avg_headcount} onChange={update('avg_headcount')} className={inputClass} />
            </Field>
          </div>
          <Field label="Describe the events you've managed">
            <textarea
              rows={4}
              value={form.events_run}
              onChange={update('events_run')}
              className={inputClass}
            />
          </Field>
          <Field
            label="Why do you want to host this event?"
            hint="If you'd rather answer on video or a voice memo, paste a direct link here (under 3 minutes)."
          >
            <textarea
              rows={4}
              value={form.motivation}
              onChange={update('motivation')}
              className={inputClass}
            />
          </Field>
        </section>

        <section className="bg-bg-surface border border-border rounded-lg p-4 space-y-4">
          <h2 className="text-base font-semibold text-text-primary">Anything else</h2>
          <Field
            label="Reference from the Explorer Series"
            hint="A Navigator, Council Member or avid player — name and email, so we can speak with them."
          >
            <input value={form.reference_contact} onChange={update('reference_contact')} className={inputClass} />
          </Field>
          <Field label="Is there anything else you'd like us to know?">
            <textarea rows={3} value={form.anything_else} onChange={update('anything_else')} className={inputClass} />
          </Field>
          <Field
            label="Another TO you think we should contact?"
            hint="Who they are, where they're located, and how to reach them."
          >
            <textarea rows={2} value={form.referral} onChange={update('referral')} className={inputClass} />
          </Field>
        </section>

        <label className="flex items-start gap-2 text-sm text-text-primary">
          <input
            type="checkbox"
            required
            checked={form.read_navigator_role}
            onChange={update('read_navigator_role')}
            className="mt-1"
          />
          <span>
            I have read the summary of the Navigator role and responsibilities, and the FAQs.{' '}
            <a
              href={NAVIGATOR_INFO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:underline"
            >
              Read it here
            </a>
            .
          </span>
        </label>

        {error && (
          <div className="text-sm rounded p-3 border bg-accent-red/10 border-accent-red/30 text-accent-red">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="px-5 py-2 text-sm bg-secondary text-black font-medium rounded hover:bg-secondary/80 disabled:opacity-40 transition-colors"
        >
          {submitting
            ? (editing ? 'Saving…' : 'Submitting…')
            : (editing ? 'Update Application' : 'Submit Application')}
        </button>
      </form>
    </div>
  )
}
