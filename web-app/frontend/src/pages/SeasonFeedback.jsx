import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import usePageTitle from '@/hooks/usePageTitle'
import { useAuth } from '@/context/AuthContext'
import Spinner from '@/components/ui/Spinner'
import {
  getSeasonFeedbackForm,
  submitSeasonFeedback,
  OTHER_PREFIX,
} from '@/api/seasonFeedback'

// The form is rendered from the schema the API returns, so the questions
// only ever live in one place (services/season_feedback.py). This page is
// not linked from the nav: the URL goes out in the season announcement.

const inputClass =
  'w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm text-text-primary' +
  ' focus:outline-none focus:border-secondary placeholder:text-text-muted/50'

function isShown(question, answers) {
  const cond = question.show_if
  if (!cond) return true
  return cond.values.includes(answers[cond.key])
}

function QuestionHeading({ question }) {
  return (
    <>
      <span className="block text-sm text-text-primary">
        {question.label}
        {question.required && <span className="text-accent-red"> *</span>}
      </span>
      {question.hint && <span className="block text-xs text-text-muted">{question.hint}</span>}
    </>
  )
}

function ScaleQuestion({ question, value, onChange }) {
  const numbers = []
  for (let n = question.min; n <= question.max; n += 1) numbers.push(n)
  const [low, high] = question.labels || []
  const isNa = value === 'N/A'

  return (
    <fieldset className="space-y-2">
      <legend className="mb-1"><QuestionHeading question={question} /></legend>
      <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label={question.label}>
        {numbers.map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            onClick={() => onChange(value === n ? null : n)}
            className={`min-w-[2.25rem] h-9 px-2 text-sm rounded border transition-colors ${
              value === n
                ? 'bg-secondary text-black border-secondary'
                : 'bg-bg-elevated border-border text-text hover:border-secondary'
            }`}
          >
            {n}
          </button>
        ))}
        {question.allow_na && (
          <button
            type="button"
            role="radio"
            aria-checked={isNa}
            onClick={() => onChange(isNa ? null : 'N/A')}
            className={`h-9 px-3 text-sm rounded border transition-colors ${
              isNa
                ? 'bg-secondary text-black border-secondary'
                : 'bg-bg-elevated border-border text-text hover:border-secondary'
            }`}
          >
            N/A
          </button>
        )}
      </div>
      {(low || high) && (
        <div className="flex justify-between text-xs text-text-muted max-w-md">
          <span>{question.min} = {low}</span>
          <span>{question.max} = {high}</span>
        </div>
      )}
    </fieldset>
  )
}

function RadioQuestion({ question, value, onChange }) {
  return (
    <fieldset className="space-y-2">
      <legend className="mb-1"><QuestionHeading question={question} /></legend>
      <div className="space-y-1.5">
        {question.options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
            <input
              type="radio"
              name={question.key}
              value={option}
              checked={value === option}
              onChange={() => onChange(option)}
              className="accent-secondary"
            />
            <span>{option}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function SelectQuestion({ question, value, onChange }) {
  return (
    <label className="block space-y-1">
      <QuestionHeading question={question} />
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        className={`${inputClass} max-w-xs`}
      >
        <option value="">Choose one</option>
        {question.options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </label>
  )
}

function CheckboxQuestion({ question, value, onChange }) {
  const chosen = value?.items || []
  const otherOn = value?.other != null
  const otherText = value?.other || ''

  const toggle = (option) => {
    const next = chosen.includes(option)
      ? chosen.filter((o) => o !== option)
      : [...chosen, option]
    onChange({ items: next, other: value?.other ?? null })
  }

  return (
    <fieldset className="space-y-2">
      <legend className="mb-1"><QuestionHeading question={question} /></legend>
      <div className="space-y-1.5">
        {question.options.map((option) => (
          <label key={option} className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
            <input
              type="checkbox"
              checked={chosen.includes(option)}
              onChange={() => toggle(option)}
              className="accent-secondary"
            />
            <span>{option}</span>
          </label>
        ))}
        {question.allow_other && (
          <div className="space-y-1.5">
            <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer">
              <input
                type="checkbox"
                checked={otherOn}
                onChange={() => onChange({ items: chosen, other: otherOn ? null : '' })}
                className="accent-secondary"
              />
              <span>Other</span>
            </label>
            {otherOn && (
              <input
                type="text"
                value={otherText}
                onChange={(e) => onChange({ items: chosen, other: e.target.value })}
                maxLength={200}
                placeholder="Tell us more"
                aria-label={`${question.label} (other)`}
                className={`${inputClass} max-w-md ml-6`}
              />
            )}
          </div>
        )}
      </div>
    </fieldset>
  )
}

function TextQuestion({ question, value, onChange }) {
  const long = question.type === 'textarea'
  const limit = long ? 2000 : 200
  const text = value || ''
  return (
    <label className="block space-y-1">
      <QuestionHeading question={question} />
      {long ? (
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          maxLength={limit}
          rows={4}
          className={`${inputClass} resize-y`}
        />
      ) : (
        <input
          type="text"
          value={text}
          onChange={(e) => onChange(e.target.value)}
          maxLength={limit}
          className={`${inputClass} max-w-md`}
        />
      )}
      {long && text.length > limit * 0.8 && (
        <span className="block text-xs text-text-muted text-right">{text.length}/{limit}</span>
      )}
    </label>
  )
}

function Question({ question, value, onChange }) {
  switch (question.type) {
    case 'scale':
      return <ScaleQuestion question={question} value={value} onChange={onChange} />
    case 'radio':
      return <RadioQuestion question={question} value={value} onChange={onChange} />
    case 'select':
      return <SelectQuestion question={question} value={value} onChange={onChange} />
    case 'checkbox':
      return <CheckboxQuestion question={question} value={value} onChange={onChange} />
    default:
      return <TextQuestion question={question} value={value} onChange={onChange} />
  }
}

/** Turn the form's working state into the answers payload the API expects. */
export function toPayload(sections, answers) {
  const payload = {}
  for (const section of sections) {
    for (const q of section.questions) {
      if (!isShown(q, answers)) continue
      const value = answers[q.key]
      if (q.type === 'checkbox') {
        const items = [...(value?.items || [])]
        const other = (value?.other || '').trim()
        if (other) items.push(OTHER_PREFIX + other)
        if (items.length) payload[q.key] = items
      } else if (q.type === 'scale') {
        if (typeof value === 'number') payload[q.key] = value
      } else if (typeof value === 'string') {
        const trimmed = value.trim()
        if (trimmed) payload[q.key] = trimmed
      }
    }
  }
  return payload
}

export default function SeasonFeedback() {
  const { user } = useAuth()
  const [form, setForm] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [answers, setAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [submitted, setSubmitted] = useState(false)

  usePageTitle(form ? `${form.season} Feedback` : 'Season Feedback')

  useEffect(() => {
    let cancelled = false
    getSeasonFeedbackForm()
      .then((data) => { if (!cancelled) setForm(data) })
      .catch(() => { if (!cancelled) setLoadError('Could not load the form. Please try again later.') })
    return () => { cancelled = true }
  }, [])

  // A logged-in player shouldn't have to retype their Discord name.
  useEffect(() => {
    if (user?.username) {
      setAnswers((prev) => (prev.discord_name ? prev : { ...prev, discord_name: user.username }))
    }
  }, [user])

  const sections = form?.sections || []

  const visibleSections = useMemo(
    () =>
      sections
        .map((section) => ({
          ...section,
          questions: section.questions.filter((q) => isShown(q, answers)),
        }))
        .filter((section) => section.questions.length > 0),
    [sections, answers],
  )

  const setAnswer = (key) => (value) => setAnswers((prev) => ({ ...prev, [key]: value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    const payload = toPayload(sections, answers)

    for (const section of sections) {
      for (const q of section.questions) {
        if (q.required && isShown(q, answers) && payload[q.key] == null) {
          setError(`Please answer: ${q.label}`)
          document.getElementById(`q-${q.key}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
          return
        }
      }
    }

    setSubmitting(true)
    setError(null)
    try {
      await submitSeasonFeedback(payload)
      setSubmitted(true)
      window.scrollTo({ top: 0 })
    } catch (err) {
      setError(err.message || 'Failed to submit. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) {
    return (
      <div className="max-w-2xl mx-auto">
        <p className="text-sm text-accent-red">{loadError}</p>
      </div>
    )
  }

  if (!form) return <Spinner className="py-12" />

  if (submitted) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <h1 className="text-2xl font-display text-secondary">{form.season} Feedback</h1>
        <div className="bg-bg-surface border border-border rounded-soft p-8 text-center space-y-4">
          <div className="text-4xl">&#10003;</div>
          <h2 className="text-xl font-semibold text-text-primary">Thank you!</h2>
          <p className="text-text-muted text-sm">
            Your answers have been recorded. They help shape the next season.
          </p>
          <Link to="/" className="inline-block mt-2 text-sm text-secondary hover:underline">
            Back to the leaderboard
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-display text-secondary">{form.season} Feedback</h1>
        <p className="text-sm text-text-muted mt-1">
          Thanks for playing this season. This takes about two minutes. Only the two
          questions marked <span className="text-accent-red">*</span> are required, so skip
          anything you like. Answers are only seen by the organizers.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {visibleSections.map((section) => (
          <section key={section.title} className="bg-bg-surface border border-border rounded-soft p-5 space-y-5">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">{section.title}</h2>
              {section.description && (
                <p className="text-xs text-text-muted">{section.description}</p>
              )}
            </div>
            {section.questions.map((q) => (
              <div key={q.key} id={`q-${q.key}`}>
                <Question question={q} value={answers[q.key]} onChange={setAnswer(q.key)} />
              </div>
            ))}
          </section>
        ))}

        {error && <p className="text-sm text-accent-red" role="alert">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full py-2.5 bg-secondary text-black rounded font-medium hover:bg-secondary/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? 'Submitting...' : 'Submit Feedback'}
        </button>
      </form>
    </div>
  )
}
