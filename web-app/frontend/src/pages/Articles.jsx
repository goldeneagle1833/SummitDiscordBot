import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listArticles, getArticleFacets, ARTICLE_CATEGORIES } from '@/api/articles'
import { useAuth } from '@/context/AuthContext'
import { ArticleCard, FeaturedArticle } from '@/components/articles/ArticleBits'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const DATE_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '30', label: 'Past month' },
  { value: '90', label: 'Past 3 months' },
  { value: '365', label: 'Past year' },
]
const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'popular', label: 'Most read' },
  { value: 'oldest', label: 'Oldest' },
]

const selectCls = 'bg-bg-elevated border border-border rounded px-2.5 py-1.5 text-sm text-text min-w-0'

export default function Articles() {
  usePageTitle('Player Articles')
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const category = params.get('category') || ''
  const tag = params.get('tag') || ''
  const author = params.get('author') || ''
  const days = params.get('days') || ''
  const sort = params.get('sort') || 'newest'

  const [search, setSearch] = useState(q)
  const [facets, setFacets] = useState(null)
  const [articles, setArticles] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(null)
  const requestId = useRef(0)

  const setParam = (key, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  // Debounced search box -> ?q=
  useEffect(() => { setSearch(q) }, [q])
  useEffect(() => {
    if (search === q) return undefined
    const t = setTimeout(() => setParam('q', search.trim()), 300)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    getArticleFacets().then(setFacets).catch(() => setFacets(null))
  }, [])

  const query = useMemo(() => ({ q, category, tag, author, days, sort }), [q, category, tag, author, days, sort])

  useEffect(() => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    listArticles({ ...query, page: 1 })
      .then((d) => {
        if (id !== requestId.current) return
        setArticles(d.articles)
        setTotal(d.total)
        setPage(1)
      })
      .catch((e) => id === requestId.current && setError(e.message))
      .finally(() => id === requestId.current && setLoading(false))
  }, [query])

  const loadMore = () => {
    setLoadingMore(true)
    listArticles({ ...query, page: page + 1 })
      .then((d) => {
        setArticles((prev) => [...prev, ...d.articles])
        setPage(page + 1)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingMore(false))
  }

  const filtered = Boolean(q || category || tag || author || days || sort !== 'newest')
  const featured = !filtered && articles.length > 2 ? articles[0] : null
  const gridArticles = featured ? articles.slice(1) : articles
  const counts = facets?.categories || {}
  const allCount = Object.values(counts).reduce((a, b) => a + b, 0)
  const authorName = facets?.authors?.find((a) => a.author_id === author)?.author_name

  const clearAll = () => {
    setSearch('')
    setParams(new URLSearchParams(), { replace: true })
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-display text-secondary">Player Articles</h1>
          <p className="text-sm text-text-muted mt-1">
            Strategy, deck guides and tournament stories written by the Summit community.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          {user && (
            <Link to="/articles/mine" className="px-3 py-2 text-sm rounded-soft border border-border hover:border-secondary transition-colors">
              My articles
            </Link>
          )}
          <Link
            to={user ? '/articles/new' : `/login?next=${encodeURIComponent('/articles/new')}`}
            className="px-3 py-2 text-sm rounded-soft bg-brand-blue text-white hover:bg-brand-blue-light font-medium transition-colors"
          >
            Write an article
          </Link>
        </div>
      </header>

      {/* Search + filters */}
      <div className="space-y-3">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="2" />
            <path d="M14 14l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search articles, authors, cards, tags…"
            aria-label="Search articles"
            className="w-full bg-bg-surface border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm focus:border-secondary/70 outline-none"
          />
        </div>

        <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap" role="tablist" aria-label="Category">
          {[''].concat(facets?.all_categories || ARTICLE_CATEGORIES).map((c) => {
            const active = category === c
            const n = c ? counts[c] || 0 : allCount
            return (
              <button
                key={c || 'all'}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setParam('category', c)}
                className={`shrink-0 px-3 py-1.5 rounded-full text-sm font-medium border transition-colors ${
                  active
                    ? 'bg-secondary/15 border-secondary text-secondary'
                    : 'border-border text-text-muted hover:text-text hover:border-text-muted'
                }`}
              >
                {c || 'All'}
                {facets && <span className="ml-1.5 text-xs opacity-70">{n}</span>}
              </button>
            )
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Author" value={author} onChange={(e) => setParam('author', e.target.value)} className={selectCls}>
            <option value="">All authors</option>
            {(facets?.authors || []).map((a) => (
              <option key={a.author_id} value={a.author_id}>{a.author_name} ({a.n})</option>
            ))}
          </select>
          <select aria-label="Published" value={days} onChange={(e) => setParam('days', e.target.value)} className={selectCls}>
            {DATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select aria-label="Sort" value={sort} onChange={(e) => setParam('sort', e.target.value === 'newest' ? '' : e.target.value)} className={selectCls}>
            {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {tag && (
            <button type="button" onClick={() => setParam('tag', '')} className="text-sm px-2.5 py-1 rounded-full border border-secondary text-secondary">
              #{tag} <span aria-hidden="true">×</span><span className="sr-only">Remove tag filter</span>
            </button>
          )}
          {filtered && (
            <button type="button" onClick={clearAll} className="text-sm text-text-muted hover:text-text underline-offset-2 hover:underline">
              Clear filters
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-6">
        {/* Results */}
        <section className="min-w-0 space-y-4" aria-live="polite">
          {loading ? (
            <Spinner className="py-16" />
          ) : error ? (
            <p className="text-red-400 text-sm">{error}</p>
          ) : articles.length === 0 ? (
            <EmptyState filtered={filtered} onClear={clearAll} user={user} />
          ) : (
            <>
              <p className="text-xs text-text-muted">
                {total} article{total === 1 ? '' : 's'}
                {authorName ? ` by ${authorName}` : ''}
                {q ? ` matching “${q}”` : ''}
              </p>
              {featured && <FeaturedArticle article={featured} />}
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {gridArticles.map((a) => (
                  <ArticleCard key={a.id} article={a} activeTag={tag} onTag={(t) => setParam('tag', t === tag ? '' : t)} />
                ))}
              </div>
              {articles.length < total && (
                <div className="flex justify-center">
                  <button
                    type="button"
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="px-4 py-2 text-sm rounded-soft border border-border hover:border-secondary disabled:opacity-40 transition-colors"
                  >
                    {loadingMore ? 'Loading…' : 'Load more articles'}
                  </button>
                </div>
              )}
            </>
          )}
        </section>

        {/* Sidebar */}
        <aside className="space-y-4 min-w-0">
          {facets?.tags?.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-lg p-4">
              <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Popular tags</h2>
              <div className="flex flex-wrap gap-1.5">
                {facets.tags.map(({ tag: t, n }) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setParam('tag', t === tag ? '' : t)}
                    className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                      t === tag ? 'border-secondary text-secondary' : 'border-border text-text-muted hover:text-text'
                    }`}
                  >
                    #{t} <span className="opacity-60">{n}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {facets?.authors?.length > 0 && (
            <div className="bg-bg-surface border border-border rounded-lg p-4">
              <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-2">Authors</h2>
              <ul className="space-y-1">
                {facets.authors.slice(0, 8).map((a) => (
                  <li key={a.author_id}>
                    <button
                      type="button"
                      onClick={() => setParam('author', a.author_id === author ? '' : a.author_id)}
                      className={`w-full flex justify-between text-sm py-0.5 ${a.author_id === author ? 'text-secondary' : 'text-text hover:text-secondary'}`}
                    >
                      <span className="truncate">{a.author_name}</span>
                      <span className="text-text-muted text-xs">{a.n}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="bg-gradient-to-br from-brand-panel to-bg-surface border border-brand-line rounded-lg p-4">
            <h2 className="font-display text-lg text-secondary">Write for the Summit</h2>
            <p className="text-sm text-text-muted mt-1">
              Share a deck guide, a tournament report or a strategy idea. A Summit reviewer reads every article before it goes live.
            </p>
            <Link
              to={user ? '/articles/new' : `/login?next=${encodeURIComponent('/articles/new')}`}
              className="inline-block mt-3 text-sm font-medium text-secondary hover:underline"
            >
              Start writing →
            </Link>
          </div>
        </aside>
      </div>
    </div>
  )
}

function EmptyState({ filtered, onClear, user }) {
  return (
    <div className="text-center py-16 bg-bg-surface border border-dashed border-border rounded-lg px-4">
      {filtered ? (
        <>
          <p className="text-text">No articles match those filters.</p>
          <button type="button" onClick={onClear} className="mt-2 text-sm text-secondary hover:underline">Clear filters</button>
        </>
      ) : (
        <>
          <p className="text-text">No articles yet. Be the first!</p>
          <Link
            to={user ? '/articles/new' : `/login?next=${encodeURIComponent('/articles/new')}`}
            className="inline-block mt-3 px-3 py-2 text-sm rounded-soft bg-brand-blue text-white hover:bg-brand-blue-light"
          >
            Write an article
          </Link>
        </>
      )}
    </div>
  )
}
