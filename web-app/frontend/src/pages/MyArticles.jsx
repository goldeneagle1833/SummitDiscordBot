import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { deleteArticle, formatArticleDate, getArticle, getMyArticles, articlePath } from '@/api/articles'
import { CategoryBadge, StatusBadge } from '@/components/articles/ArticleBits'
import CommentThread from '@/components/articles/CommentThread'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function MyArticles() {
  usePageTitle('My articles')
  const [params, setParams] = useSearchParams()
  const openId = parseInt(params.get('id') || '', 10) || null
  const sent = params.get('sent') === '1'
  const [articles, setArticles] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  const load = () => getMyArticles().then((d) => setArticles(d.articles)).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  useEffect(() => {
    setDetail(null)
    if (openId) getArticle(openId).then(setDetail).catch(() => setDetail(null))
  }, [openId])

  const open = (id) => {
    const next = new URLSearchParams()
    if (id && id !== openId) next.set('id', String(id))
    setParams(next, { replace: true })
  }

  const remove = async (a) => {
    if (!window.confirm(`Delete "${a.title}"? This can't be undone.`)) return
    try {
      await deleteArticle(a.id)
      if (openId === a.id) open(null)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link to="/articles" className="text-sm text-text-muted hover:text-secondary">← All articles</Link>
          <h1 className="text-2xl font-display text-secondary mt-1">My articles</h1>
        </div>
        <Link to="/articles/new" className="px-3 py-2 text-sm rounded-soft bg-brand-blue text-white hover:bg-brand-blue-light font-medium">
          Write an article
        </Link>
      </div>

      {sent && (
        <p className="text-sm rounded-lg border border-accent-green/50 bg-accent-green/10 text-green-300 px-3 py-2">
          Sent for review. The Summit reviewers have been notified, and their comments will show here.
        </p>
      )}
      {error && <p className="text-sm text-red-400">{error}</p>}

      {articles === null ? (
        <Spinner className="py-16" />
      ) : articles.length === 0 ? (
        <p className="text-text-muted text-sm py-10 text-center">You haven't written any articles yet.</p>
      ) : (
        <ul className="space-y-3">
          {articles.map((a) => {
            const expanded = openId === a.id
            return (
              <li key={a.id} className={`bg-bg-surface border rounded-lg ${expanded ? 'border-secondary/50' : 'border-border'}`}>
                <button type="button" onClick={() => open(a.id)} className="w-full text-left p-4 flex flex-col sm:flex-row sm:items-center gap-2" aria-expanded={expanded}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <StatusBadge status={a.status} />
                      <CategoryBadge category={a.category} />
                    </div>
                    <p className="font-semibold text-text-primary break-words">{a.title}</p>
                    <p className="text-xs text-text-muted">
                      Sent {formatArticleDate(a.submitted_at)}
                      {a.status === 'approved' && a.view_count > 0 ? ` · ${a.view_count} reads` : ''}
                    </p>
                  </div>
                  <span className="text-xs text-text-muted shrink-0">{expanded ? 'Hide' : 'Comments and actions'}</span>
                </button>
                {expanded && (
                  <div className="border-t border-border p-4 space-y-4">
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Link to={articlePath(a)} className="px-3 py-1.5 rounded border border-border hover:border-secondary">
                        {a.status === 'approved' ? 'View' : 'Preview'}
                      </Link>
                      <Link to={`/articles/${a.id}/edit`} className="px-3 py-1.5 rounded border border-border hover:border-secondary">Edit</Link>
                      <button type="button" onClick={() => remove(a)} className="px-3 py-1.5 rounded border border-border text-red-400 hover:border-accent-red">Delete</button>
                    </div>
                    <div>
                      <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Review conversation</h2>
                      {detail?.id === a.id ? (
                        <CommentThread
                          articleId={a.id}
                          comments={detail.comments}
                          viewerRole="author"
                          onChange={(comments) => setDetail({ ...detail, comments })}
                        />
                      ) : <Spinner className="py-6" />}
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
