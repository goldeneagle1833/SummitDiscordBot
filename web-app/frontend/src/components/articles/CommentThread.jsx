import { useState } from 'react'
import { addArticleComment, formatArticleDate } from '@/api/articles'

const EVENT_TEXT = {
  submitted: 'sent it for review',
  changes_requested: 'requested changes',
  approved: 'approved and published it',
  rejected: 'did not approve it',
}

/**
 * Private conversation between the author and the reviewers. Reviewer
 * comments are DM'd to the author by the bot (Discord logins).
 */
export default function CommentThread({ articleId, comments, onChange, viewerRole }) {
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const send = async () => {
    if (!text.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await addArticleComment(articleId, text.trim())
      setText('')
      onChange?.(res.comments)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      {comments?.length ? (
        <ol className="space-y-2">
          {comments.map((c) => {
            const reviewer = c.role === 'reviewer'
            const event = EVENT_TEXT[c.kind]
            return (
              <li
                key={c.id}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  reviewer ? 'border-secondary/30 bg-secondary/5' : 'border-border bg-bg-elevated/50'
                }`}
              >
                <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-text-muted">
                  <span className={`font-semibold ${reviewer ? 'text-secondary' : 'text-text'}`}>{c.username}</span>
                  <span>{reviewer ? 'Reviewer' : 'Author'}</span>
                  {event && <span>· {event}</span>}
                  <span className="ml-auto">{formatArticleDate(c.created_at)}</span>
                </div>
                {c.body && <p className="mt-1 whitespace-pre-wrap break-words text-text-primary">{c.body}</p>}
              </li>
            )
          })}
        </ol>
      ) : (
        <p className="text-sm text-text-muted">No comments yet.</p>
      )}
      <div>
        <label htmlFor={`comment-${articleId}`} className="sr-only">Comment</label>
        <textarea
          id={`comment-${articleId}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder={viewerRole === 'reviewer' ? 'Comment for the author (sent to them on Discord)' : 'Reply to the reviewers'}
          className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
        />
        {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
        <div className="flex justify-end mt-1">
          <button
            type="button"
            onClick={send}
            disabled={saving || !text.trim()}
            className="px-3 py-1.5 text-sm bg-bg-elevated border border-border rounded hover:border-secondary disabled:opacity-40 transition-colors"
          >
            {saving ? 'Sending…' : 'Send comment'}
          </button>
        </div>
      </div>
    </div>
  )
}
