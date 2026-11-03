import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getArticle, listArticles, articlePdfUrl, formatArticleDate } from '@/api/articles'
import {
  ArticleBody, ArticleCard, AuthorChip, CategoryBadge, StatusBadge, TagList,
} from '@/components/articles/ArticleBits'
import Discussion from '@/components/articles/Discussion'
import ShareLinkButton from '@/components/ui/ShareLinkButton'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

export default function ArticleDetail() {
  const { slug } = useParams()
  const id = parseInt(slug, 10)
  const [article, setArticle] = useState(null)
  const [more, setMore] = useState([])
  const [error, setError] = useState(null)
  usePageTitle(article?.title || 'Player Articles')

  useEffect(() => {
    setArticle(null)
    setError(null)
    if (!id) {
      setError('Article not found')
      return
    }
    getArticle(id)
      .then((a) => {
        setArticle(a)
        listArticles({ author: a.author_id })
          .then((d) => setMore(d.articles.filter((x) => x.id !== a.id).slice(0, 3)))
          .catch(() => {})
      })
      .catch((e) => setError(e.status === 404 ? 'Article not found' : e.message))
  }, [id])

  if (error) {
    return (
      <div className="max-w-3xl mx-auto text-center py-16">
        <p className="text-text">{error}</p>
        <Link to="/articles" className="text-secondary hover:underline text-sm mt-2 inline-block">Back to all articles</Link>
      </div>
    )
  }
  if (!article) return <Spinner className="py-20" />

  const path = `/articles/${article.id}-${article.slug}`
  const unpublished = article.status && article.status !== 'approved'

  return (
    <div className="max-w-3xl mx-auto">
      <Link to="/articles" className="text-sm text-text-muted hover:text-secondary">← All articles</Link>

      {unpublished && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-secondary/40 bg-secondary/5 px-3 py-2 text-sm">
          <StatusBadge status={article.status} />
          <span className="text-text-muted">Only you and the reviewers can see this.</span>
          <span className="ml-auto flex gap-3">
            {article.can_edit && <Link to={`/articles/${article.id}/edit`} className="text-secondary hover:underline">Edit</Link>}
            {article.is_reviewer && <Link to={`/admin/articles?id=${article.id}`} className="text-secondary hover:underline">Review</Link>}
          </span>
        </div>
      )}

      <article className="mt-4">
        <header className="pb-5 border-b border-border">
          <CategoryBadge category={article.category} />
          <h1 className="mt-3 text-3xl sm:text-4xl font-display text-text-primary leading-tight break-words">{article.title}</h1>
          <p className="mt-3 text-lg text-text-muted break-words">{article.summary}</p>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <AuthorChip article={article} size="md" />
            <span className="text-text-muted">
              {formatArticleDate(article.published_at || article.updated_at)} · {article.reading_minutes} min read
              {article.view_count > 0 && ` · ${article.view_count.toLocaleString()} reads`}
            </span>
            {!unpublished && (
              <ShareLinkButton
                path={path}
                hint="Copy a link to this article"
                nativeShare
                shareTitle={article.title}
                shareText={article.summary}
                className="ml-auto"
              />
            )}
          </div>
          <div className="mt-3"><TagList tags={article.tags} /></div>
        </header>

        {article.has_pdf && (
          <a
            href={articlePdfUrl(article.id)}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-5 flex items-center gap-3 rounded-lg border border-border bg-bg-surface px-4 py-3 hover:border-secondary/60 transition-colors"
          >
            <span className="w-10 h-12 rounded bg-accent-red/20 text-red-300 text-xs font-bold flex items-center justify-center shrink-0">PDF</span>
            <span className="min-w-0">
              <span className="block font-medium text-text-primary">Read the PDF version</span>
              <span className="block text-xs text-text-muted">
                Opens in a new tab{article.pdf_size ? ` · ${(article.pdf_size / (1024 * 1024)).toFixed(1)} MB` : ''}
              </span>
            </span>
          </a>
        )}

        {article.body_html && (
          <div className="mt-6">
            <ArticleBody html={article.body_html} />
          </div>
        )}
      </article>

      {!unpublished && <Discussion articleId={article.id} />}

      {more.length > 0 && (
        <section className="mt-12 pt-6 border-t border-border">
          <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">More from {article.author_name}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {more.map((a) => <ArticleCard key={a.id} article={a} />)}
          </div>
        </section>
      )}
    </div>
  )
}
