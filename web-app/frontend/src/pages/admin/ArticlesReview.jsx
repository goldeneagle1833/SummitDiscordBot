import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  articlePath, articlePdfUrl, deleteArticle, formatArticleDate, getArticle,
  getReviewQueue, reviewArticle,
} from '@/api/articles'
import { ArticleBody, ArticleImage, AuthorChip, CategoryBadge, LinkedArticleTile, StatusBadge, TagList } from '@/components/articles/ArticleBits'
import CommentThread from '@/components/articles/CommentThread'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const TABS = [
  { key: 'pending', label: 'Waiting' },
  { key: 'changes_requested', label: 'Changes requested' },
  { key: 'approved', label: 'Published' },
  { key: 'rejected', label: 'Not approved' },
]

export default function ArticlesReview() {
  usePageTitle('Article review')
  const [params, setParams] = useSearchParams()
  const selectedId = parseInt(params.get('id') || '', 10) || null
  const [status, setStatus] = useState('pending')
  const [queue, setQueue] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)

  const loadQueue = useCallback(() => {
    getReviewQueue(status).then(setQueue).catch((e) => setError(e.message))
  }, [status])
  useEffect(() => { loadQueue() }, [loadQueue])

  const loadSelected = useCallback(() => {
    if (!selectedId) { setSelected(null); return }
    getArticle(selectedId).then((a) => {
      setSelected(a)
      // Opening a DM link lands on the right tab
      if (a.status && a.status !== status) setStatus(a.status)
    }).catch((e) => setError(e.message))
  }, [selectedId]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadSelected() }, [loadSelected])

  const select = (id) => {
    const next = new URLSearchParams(params)
    if (id) next.set('id', String(id))
    else next.delete('id')
    setParams(next, { replace: true })
  }

  const counts = queue?.counts || {}

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div>
        <Link to="/admin" className="text-sm text-text-muted hover:text-secondary">← Admin</Link>
        <h1 className="text-2xl font-display text-secondary mt-1">Player article review</h1>
        <p className="text-sm text-text-muted">Approve articles for the blog, or comment and ask for changes. Comments are DM'd to the author (Discord logins).</p>
      </div>
      {queue && !queue.reviewers_configured && (
        <p className="text-sm rounded-lg border border-secondary/40 bg-secondary/5 px-3 py-2">
          No reviewer Discord IDs are set, so nobody gets a DM for new articles. Set ARTICLE_REVIEWER_IDS on the server.
        </p>
      )}
      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex gap-1.5 overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={status === t.key}
            onClick={() => setStatus(t.key)}
            className={`shrink-0 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
              status === t.key ? 'bg-secondary/15 border-secondary text-secondary' : 'border-border text-text-muted hover:text-text'
            }`}
          >
            {t.label}
            <span className="ml-1.5 text-xs opacity-70">{counts[t.key] ?? ''}</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4 items-start">
        <ul className={`space-y-2 min-w-0 ${selectedId ? 'hidden lg:block' : ''}`}>
          {queue === null ? <Spinner className="py-10" /> : queue.articles.length === 0 ? (
            <li className="text-sm text-text-muted py-8 text-center bg-bg-surface border border-border rounded-lg">Nothing here.</li>
          ) : queue.articles.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => select(a.id)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  a.id === selectedId ? 'border-secondary bg-secondary/5' : 'border-border bg-bg-surface hover:border-text-muted'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <CategoryBadge category={a.category} />
                  {a.has_pdf && <span className="text-[11px] font-semibold text-red-300">PDF</span>}
                  {a.external_url && <span className="text-[11px] font-semibold text-sky-300">Link</span>}
                  <span className="ml-auto text-xs text-text-muted">{formatArticleDate(a.submitted_at)}</span>
                </div>
                <p className="font-semibold text-text-primary text-sm break-words">{a.title}</p>
                <p className="text-xs text-text-muted truncate">by {a.author_name} · {a.word_count.toLocaleString()} words</p>
              </button>
            </li>
          ))}
        </ul>

        <section className="min-w-0">
          {!selectedId ? (
            <div className="hidden lg:flex items-center justify-center h-64 border border-dashed border-border rounded-lg text-sm text-text-muted">
              Pick an article to review
            </div>
          ) : !selected ? <Spinner className="py-16" /> : (
            <ReviewPanel
              article={selected}
              onBack={() => select(null)}
              onChanged={() => { loadSelected(); loadQueue() }}
              onDeleted={() => { select(null); loadQueue() }}
              setComments={(comments) => setSelected({ ...selected, comments })}
            />
          )}
        </section>
      </div>
    </div>
  )
}

function ReviewPanel({ article, onBack, onChanged, onDeleted, setComments }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)

  const act = async (action) => {
    if ((action === 'request_changes' || action === 'reject') && !note.trim()) {
      setError(action === 'reject' ? 'Give the author a reason.' : 'Say what should change.')
      return
    }
    setBusy(action)
    setError(null)
    try {
      await reviewArticle(article.id, action, note.trim())
      setNote('')
      onChanged()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(null)
    }
  }

  const remove = async () => {
    if (!window.confirm(`Delete "${article.title}" for good? The author is not told.`)) return
    setBusy('delete')
    try {
      await deleteArticle(article.id)
      onDeleted()
    } catch (e) {
      setError(e.message)
      setBusy(null)
    }
  }

  const live = article.status === 'approved'

  return (
    <div className="bg-bg-surface border border-border rounded-lg">
      <div className="p-4 border-b border-border space-y-2">
        <button type="button" onClick={onBack} className="lg:hidden text-sm text-text-muted hover:text-secondary">← Back to list</button>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={article.status} />
          <CategoryBadge category={article.category} />
          <Link to={articlePath(article)} className="ml-auto text-sm text-secondary hover:underline">Open article page</Link>
        </div>
        <h2 className="text-xl font-semibold text-text-primary break-words">{article.title}</h2>
        <p className="text-sm text-text-muted break-words">{article.summary}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <AuthorChip article={article} />
          <span className="text-text-muted text-xs">
            {article.author_provider === 'discord' ? 'Discord login (gets DMs)' : 'Google login (no DMs, sees comments on the site)'}
          </span>
          <span className="text-text-muted text-xs">{article.word_count.toLocaleString()} words</span>
        </div>
        <TagList tags={article.tags} />
        {article.has_pdf && (
          <a href={articlePdfUrl(article.id)} target="_blank" rel="noopener noreferrer" className="inline-block text-sm text-secondary hover:underline">
            Open attached PDF ({article.pdf_original_name || 'article.pdf'}) ↗
          </a>
        )}
      </div>

      <div className="p-4 max-h-[60vh] overflow-y-auto border-b border-border">
        {article.header_image && !article.external_url && (
          <div className="mb-4 max-w-md">
            <p className="text-xs text-text-muted mb-1">Header card: {article.header_card}</p>
            <ArticleImage article={article} className="aspect-[2.4/1] rounded border border-border" />
          </div>
        )}
        {article.external_url && (
          <div className="mb-4 max-w-md">
            <p className="text-xs text-text-muted mb-1 break-all">Links to {article.external_url}</p>
            <LinkedArticleTile url={article.external_url} site={article.external_site} image={article.external_image} title={article.title} />
          </div>
        )}
        {article.body_html
          ? <ArticleBody html={article.body_html} />
          : <p className="text-sm text-text-muted">{article.external_url ? 'No note, link only.' : 'No text, PDF only.'}</p>}
      </div>

      <div className="p-4 border-b border-border space-y-2">
        <label htmlFor="review-note" className="block text-xs font-bold text-text-muted uppercase tracking-wider">Decision</label>
        <textarea
          id="review-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder="Note to the author (needed to request changes or reject; optional when approving)"
          className="w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm"
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex flex-wrap gap-2">
          {!live && (
            <button type="button" disabled={Boolean(busy)} onClick={() => act('approve')} className="px-3 py-1.5 text-sm rounded bg-accent-green text-white hover:bg-green-600 disabled:opacity-40">
              {busy === 'approve' ? 'Publishing…' : 'Approve and publish'}
            </button>
          )}
          <button type="button" disabled={Boolean(busy)} onClick={() => act('request_changes')} className="px-3 py-1.5 text-sm rounded border border-secondary text-secondary hover:bg-secondary/10 disabled:opacity-40">
            Request changes
          </button>
          <button type="button" disabled={Boolean(busy)} onClick={() => act('reject')} className="px-3 py-1.5 text-sm rounded border border-accent-red text-red-300 hover:bg-accent-red/10 disabled:opacity-40">
            {live ? 'Take down' : 'Reject'}
          </button>
          <button type="button" disabled={Boolean(busy)} onClick={remove} className="ml-auto px-3 py-1.5 text-sm rounded text-text-muted hover:text-red-400 disabled:opacity-40">
            Delete
          </button>
        </div>
      </div>

      <div className="p-4">
        <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Conversation with the author</h3>
        <CommentThread articleId={article.id} comments={article.comments} viewerRole="reviewer" onChange={setComments} />
      </div>
    </div>
  )
}
