import { useEffect, useState } from 'react'
import Spinner from '@/components/ui/Spinner'
import {
  getSeasonFeedbackResponses,
  deleteSeasonFeedbackResponse,
  seasonFeedbackExportUrl,
} from '@/api/seasonFeedback'

export const SEASON_FEEDBACK_PATH = '/season-feedback'

function formatAnswer(value) {
  if (value == null || value === '') return null
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

function ScaleSummary({ stat }) {
  if (!stat.count) return <p className="text-xs text-text-muted">No answers yet</p>
  const pct = ((stat.average - stat.min) / (stat.max - stat.min)) * 100
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-bg-surface rounded overflow-hidden">
        <div className="h-full bg-secondary" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm text-text-primary font-medium whitespace-nowrap">
        {stat.average} / {stat.max}
      </span>
      <span className="text-xs text-text-muted whitespace-nowrap">{stat.count} answered</span>
    </div>
  )
}

function ChoiceSummary({ question, stat }) {
  // Flask sorts JSON keys, so keep the order the question lists its options in.
  const order = [...question.options, ...(question.allow_other ? ['Other'] : [])]
  const entries = order.map((option) => [option, stat.counts[option] || 0])
  const top = Math.max(1, ...entries.map(([, n]) => n))
  if (!stat.count) return <p className="text-xs text-text-muted">No answers yet</p>
  return (
    <div className="space-y-1">
      {entries.map(([option, n]) => (
        <div key={option} className="flex items-center gap-2 text-xs">
          <span className="w-56 truncate text-text-muted" title={option}>{option}</span>
          <div className="flex-1 h-2 bg-bg-surface rounded overflow-hidden">
            <div className="h-full bg-primary" style={{ width: `${(n / top) * 100}%` }} />
          </div>
          <span className="w-8 text-right text-text-primary">{n}</span>
        </div>
      ))}
      <p className="text-xs text-text-muted/70">{stat.count} answered</p>
    </div>
  )
}

function SummaryView({ sections, summary, responses }) {
  return (
    <div className="space-y-5">
      {sections.map((section) => (
        <div key={section.title} className="space-y-3">
          <h3 className="text-sm font-semibold text-secondary">{section.title}</h3>
          {section.questions.map((q) => {
            const stat = summary[q.key]
            if (!stat) return null
            return (
              <div key={q.key} className="bg-bg-elevated border border-border rounded p-3 space-y-2">
                <p className="text-sm text-text-primary">{q.label}</p>
                {stat.type === 'scale' && <ScaleSummary stat={stat} />}
                {stat.type === 'choice' && <ChoiceSummary question={q} stat={stat} />}
                {stat.type === 'text' && (
                  <TextAnswers question={q} responses={responses} count={stat.count} />
                )}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function TextAnswers({ question, responses, count }) {
  const [open, setOpen] = useState(false)
  const items = responses
    .map((r) => ({ id: r.id, who: r.username || r.answers.discord_name, text: r.answers[question.key] }))
    .filter((item) => item.text)
  if (!count) return <p className="text-xs text-text-muted">No answers yet</p>
  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs text-primary hover:underline"
      >
        {open ? 'Hide' : 'Show'} {count} answer{count === 1 ? '' : 's'}
      </button>
      {open && (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li key={item.id} className="text-xs text-text-primary bg-bg-surface rounded px-2 py-1.5 whitespace-pre-wrap">
              {item.text}
              {item.who && <span className="text-text-muted"> — {item.who}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ResponseCard({ response, questions, onDelete }) {
  const [open, setOpen] = useState(false)
  const a = response.answers
  const who = response.username || a.discord_name || 'Anonymous'
  const answered = questions.filter((q) => formatAnswer(a[q.key]) != null)

  return (
    <div className="bg-bg-elevated border border-border rounded">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-3 py-2 text-left"
      >
        <div className="min-w-0">
          <span className="text-sm text-text-primary font-medium">{who}</span>
          <span className="text-xs text-text-muted ml-2">
            {new Date(response.created_at).toLocaleString()}
          </span>
          <p className="text-xs text-text-muted truncate">
            {a.seasons_played ? `Seasons: ${a.seasons_played}` : 'Seasons: ?'}
            {a.enjoyment != null && ` · Enjoyment ${a.enjoyment}/10`}
            {a.negative_interactions && a.negative_interactions !== 'No' && (
              <span className="text-accent-red"> · {a.negative_interactions}</span>
            )}
          </p>
        </div>
        <span className="text-xs text-text-muted whitespace-nowrap">
          {answered.length} answers {open ? '▾' : '▸'}
        </span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2 space-y-2">
          <dl className="space-y-1.5">
            {answered.map((q) => (
              <div key={q.key}>
                <dt className="text-xs text-text-muted">{q.label}</dt>
                <dd className="text-sm text-text-primary whitespace-pre-wrap">{formatAnswer(a[q.key])}</dd>
              </div>
            ))}
          </dl>
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={() => onDelete(response.id)}
              className="text-xs text-text-muted hover:text-accent-red"
            >
              Delete response
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function SeasonFeedbackSection() {
  const [season, setSeason] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState('summary')

  const load = async (which) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getSeasonFeedbackResponses(which)
      setData(result)
      setSeason(result.season)
    } catch (err) {
      setError(err.message || 'Failed to load season feedback')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load('') }, [])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this response? This cannot be undone.')) return
    try {
      await deleteSeasonFeedbackResponse(id)
      load(season)
    } catch (err) {
      setError(err.message || 'Failed to delete response')
    }
  }

  if (loading && !data) return <Spinner className="py-6" />
  if (error && !data) return <p className="text-sm text-accent-red">{error}</p>

  const responses = data?.responses || []
  const questions = (data?.sections || []).flatMap((s) => s.questions)
  const formUrl = `${window.location.origin}${SEASON_FEEDBACK_PATH}`

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={season}
          onChange={(e) => load(e.target.value)}
          aria-label="Season"
          className="bg-bg-elevated border border-border rounded px-2 py-1.5 text-sm text-text-primary"
        >
          {(data?.seasons?.length ? data.seasons : [data?.current_season]).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <span className="text-sm text-text-muted">
          {responses.length} response{responses.length === 1 ? '' : 's'}
        </span>
        <div className="flex-1" />
        <div className="flex rounded border border-border overflow-hidden text-sm">
          {['summary', 'responses'].map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              className={`px-3 py-1.5 capitalize ${
                view === v ? 'bg-secondary text-black' : 'bg-bg-elevated text-text-muted hover:text-text'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
        <a
          href={seasonFeedbackExportUrl(season)}
          className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary text-text-primary transition-colors"
        >
          Export CSV
        </a>
      </div>

      <p className="text-xs text-text-muted">
        Share this link in the season announcement:{' '}
        <code className="text-text-primary select-all">{formUrl}</code>
        {data?.current_season && data.current_season !== season && (
          <span> (the form currently collects for {data.current_season})</span>
        )}
      </p>

      {error && <p className="text-sm text-accent-red">{error}</p>}

      {responses.length === 0 ? (
        <p className="text-sm text-text-muted">No responses for this season yet.</p>
      ) : view === 'summary' ? (
        <SummaryView sections={data.sections} summary={data.summary} responses={responses} />
      ) : (
        <div className="space-y-2">
          {responses.map((r) => (
            <ResponseCard key={r.id} response={r} questions={questions} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  )
}
