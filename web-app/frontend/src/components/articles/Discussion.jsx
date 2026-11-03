import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteDiscussionComment, getDiscussion, postDiscussion } from '@/api/articles'
import { useAuth } from '@/context/AuthContext'
import LinkifiedText from '@/components/ui/LinkifiedText'

function timeAgo(iso) {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function DiscordMark() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden="true">
      <path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.6 1.3a18.3 18.3 0 0 0-5.5 0L8.6 3a19.7 19.7 0 0 0-4.9 1.5C.6 9.1-.3 13.6.1 18.1a19.9 19.9 0 0 0 6 3l1.3-2a12.9 12.9 0 0 1-2-1l.5-.4a14.2 14.2 0 0 0 12.2 0l.5.4a12.9 12.9 0 0 1-2 1l1.3 2a19.8 19.8 0 0 0 6-3c.5-5.2-.9-9.7-3.6-13.7ZM8 15.4c-1.2 0-2.2-1.1-2.2-2.4S6.8 10.6 8 10.6s2.2 1.1 2.2 2.4-1 2.4-2.2 2.4Zm8 0c-1.2 0-2.2-1.1-2.2-2.4s1-2.4 2.2-2.4 2.2 1.1 2.2 2.4-1 2.4-2.2 2.4Z" />
    </svg>
  )
}

/**
 * Comments under a published article. Every comment also appears in the
 * article's Discord forum thread, and replies there show up here (the bot
 * keeps the two in sync).
 */
export default function Discussion({ articleId }) {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    getDiscussion(articleId).then(setData).catch(() => {})
  }, [articleId])

  useEffect(() => {
    load()
    // Pick up replies from Discord while the page is open
    const t = setInterval(() => { if (document.visibilityState === 'visible') load() }, 60000)
    return () => clearInterval(t)
  }, [load])

  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setSaving(true)
    setError(null)
    try {
      setData(await postDiscussion(articleId, text.trim()))
      setText('')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const remove = async (c) => {
    if (!window.confirm('Delete this comment? It is removed from Discord too.')) return
    try {
      setData(await deleteDiscussionComment(articleId, c.id))
    } catch (err) {
      setError(err.message)
    }
  }

  const comments = data?.comments || []

  return (
    <section className="mt-12 pt-6 border-t border-border" aria-labelledby="discussion-heading">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 id="discussion-heading" className="text-xl font-semibold text-text-primary">
          Comments {comments.length > 0 && <span className="text-text-muted font-normal">({comments.length})</span>}
        </h2>
        {data?.discord_thread_url && (
          <a
            href={data.discord_thread_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-full border border-[#5865F2]/60 text-[#aab2ff] hover:bg-[#5865F2]/15 transition-colors"
          >
            <DiscordMark /> Discuss on Discord
          </a>
        )}
      </div>

      {user ? (
        <form onSubmit={send} className="mb-6">
          <label htmlFor="discussion-box" className="sr-only">Your comment</label>
          <textarea
            id="discussion-box"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={1000}
            placeholder="Add a comment. It also posts in the article's Discord thread."
            className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm focus:border-secondary/70 outline-none"
          />
          {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-text-muted">{text.length}/1000</span>
            <button
              type="submit"
              disabled={saving || !text.trim()}
              className="px-3 py-1.5 text-sm rounded-soft bg-brand-blue text-white hover:bg-brand-blue-light disabled:opacity-40 transition-colors"
            >
              {saving ? 'Posting…' : 'Post comment'}
            </button>
          </div>
        </form>
      ) : (
        <p className="mb-6 text-sm text-text-muted">
          <Link to={`/login?next=${encodeURIComponent(window.location.pathname)}`} className="text-secondary hover:underline">Log in</Link>
          {' '}to comment{data?.discord_thread_url ? ', or reply in the Discord thread' : ''}.
        </p>
      )}

      {data && comments.length === 0 && (
        <p className="text-sm text-text-muted">No comments yet. Start the conversation.</p>
      )}
      <ol className="space-y-4">
        {comments.map((c) => (
          <li key={c.id} className="flex gap-3">
            {c.avatar ? (
              <img src={c.avatar} alt="" className="w-8 h-8 rounded-full object-cover bg-bg-elevated shrink-0" loading="lazy" />
            ) : (
              <span className="w-8 h-8 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xs font-semibold text-text-muted shrink-0" aria-hidden="true">
                {(c.username || '?').slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="font-semibold text-text-primary">{c.username}</span>
                {c.source === 'discord' && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-[#aab2ff]"><DiscordMark /> via Discord</span>
                )}
                <span className="text-xs text-text-muted">{timeAgo(c.created_at)}{c.edited_at ? ' · edited' : ''}</span>
                {c.can_delete && (
                  <button type="button" onClick={() => remove(c)} className="ml-auto text-xs text-text-muted hover:text-red-400">
                    Delete
                  </button>
                )}
              </div>
              <p className="mt-0.5 text-sm text-text whitespace-pre-wrap break-words">
                <LinkifiedText text={c.body} />
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}
