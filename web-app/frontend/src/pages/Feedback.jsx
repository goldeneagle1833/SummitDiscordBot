import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import usePageTitle from '@/hooks/usePageTitle'

const FEEDBACK_TYPES = [
  { value: 'feature_request', label: 'Feature Request' },
  { value: 'bug_report', label: 'Bug Report' },
  { value: 'general', label: 'General Feedback' },
]

export default function Feedback() {
  usePageTitle('Feedback')
  const { user } = useAuth()
  const [type, setType] = useState('general')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!title.trim() || !description.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch('/api/feedback/feedback', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, title: title.trim(), description: description.trim() }),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        setSubmitted(true)
      } else {
        setError(data.error || 'Failed to submit feedback')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <h1 className="text-2xl font-display text-secondary">Feedback</h1>
        <div className="bg-bg-surface border border-border rounded-soft p-8 text-center space-y-4">
          <div className="text-4xl">&#10003;</div>
          <h2 className="text-xl font-semibold text-text-primary">Thank you for your feedback!</h2>
          <p className="text-text-muted text-sm">
            Your submission has been received and will be reviewed by the team.
            {user && ' Since you are logged in, we will notify you via Discord when your item is resolved.'}
          </p>
          <button
            onClick={() => { setSubmitted(false); setTitle(''); setDescription(''); setType('general') }}
            className="mt-4 px-4 py-2 bg-secondary text-black rounded hover:bg-secondary/80 transition-colors text-sm"
          >
            Submit Another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-display text-secondary">Feedback</h1>
      <p className="text-text-muted text-sm">
        Have an idea, found a bug, or just want to share your thoughts? Let us know!
        {user
          ? ' You are logged in — we will notify you on Discord when your feedback is resolved.'
          : ' Log in to receive a Discord notification when your feedback is resolved.'}
      </p>

      <form onSubmit={handleSubmit} className="bg-bg-surface border border-border rounded-soft p-6 space-y-4">
        {/* Type */}
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">Type</label>
          <div className="flex gap-2">
            {FEEDBACK_TYPES.map((ft) => (
              <button
                key={ft.value}
                type="button"
                onClick={() => setType(ft.value)}
                className={`px-3 py-1.5 text-sm rounded border transition-colors ${
                  type === ft.value
                    ? 'bg-secondary text-black border-secondary'
                    : 'bg-bg-elevated border-border text-text hover:border-secondary'
                }`}
              >
                {ft.label}
              </button>
            ))}
          </div>
        </div>

        {/* Title */}
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">
            Title <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Short summary of your feedback"
            maxLength={200}
            required
            className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm text-text-primary placeholder:text-text-muted/50 focus:outline-none focus:border-secondary"
          />
          <span className="text-xs text-text-muted mt-0.5 block text-right">{title.length}/200</span>
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-medium text-text-muted mb-1">
            Description <span className="text-red-400">*</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={
              type === 'bug_report'
                ? 'What happened? What did you expect? Steps to reproduce...'
                : type === 'feature_request'
                ? 'Describe the feature you would like to see...'
                : 'Tell us what you think...'
            }
            maxLength={2000}
            rows={5}
            required
            className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm text-text-primary placeholder:text-text-muted/50 resize-none focus:outline-none focus:border-secondary"
          />
          <span className="text-xs text-text-muted mt-0.5 block text-right">{description.length}/2000</span>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !title.trim() || !description.trim()}
          className="w-full py-2.5 bg-secondary text-black rounded font-medium hover:bg-secondary/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? 'Submitting...' : 'Submit Feedback'}
        </button>
      </form>
    </div>
  )
}
