import { useState } from 'react'
import { Link } from 'react-router-dom'
import NewTag from '@/components/common/NewTag'
import { useIsNew } from '@/hooks/useNewContent'
import { articleImage, articlePath, formatArticleDate, STATUS_LABELS } from '@/api/articles'

// One colour per category, used for the badge and the card's top stripe.
const CATEGORY_COLORS = {
  Strategy: { badge: 'bg-primary/15 text-primary-light', stripe: 'bg-primary' },
  'Deck Guide': { badge: 'bg-secondary/15 text-secondary', stripe: 'bg-secondary' },
  'Tournament Report': { badge: 'bg-orange-400/15 text-orange-300', stripe: 'bg-orange-400' },
  'Limited & Draft': { badge: 'bg-emerald-400/15 text-emerald-300', stripe: 'bg-emerald-400' },
  'Lore & Art': { badge: 'bg-fuchsia-400/15 text-fuchsia-300', stripe: 'bg-fuchsia-400' },
  Community: { badge: 'bg-sky-400/15 text-sky-300', stripe: 'bg-sky-400' },
  Other: { badge: 'bg-bg-elevated text-text-muted', stripe: 'bg-border' },
}

export function categoryColors(category) {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS.Other
}

export function CategoryBadge({ category, className = '' }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${categoryColors(category).badge} ${className}`}>
      {category}
    </span>
  )
}

const STATUS_STYLES = {
  pending: 'bg-primary/15 text-primary-light',
  changes_requested: 'bg-secondary/15 text-secondary',
  approved: 'bg-accent-green/20 text-green-300',
  rejected: 'bg-accent-red/20 text-red-300',
}

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${STATUS_STYLES[status] || ''}`}>
      {STATUS_LABELS[status] || status}
    </span>
  )
}

export function AuthorChip({ article, size = 'sm', link = true }) {
  const dims = size === 'md' ? 'w-9 h-9' : 'w-6 h-6'
  const initial = (article.author_name || '?').slice(0, 1).toUpperCase()
  const avatar = article.author_avatar ? (
    <img src={article.author_avatar} alt="" className={`${dims} rounded-full object-cover bg-bg-elevated shrink-0`} loading="lazy" />
  ) : (
    <span className={`${dims} rounded-full bg-bg-elevated border border-border flex items-center justify-center text-xs font-semibold text-text-muted shrink-0`} aria-hidden="true">
      {initial}
    </span>
  )
  // Discord authors have a player profile; Google logins do not.
  const name = link && article.author_provider === 'discord'
    ? <Link to={`/player/${article.author_id}`} className="hover:text-secondary truncate">{article.author_name}</Link>
    : <span className="truncate">{article.author_name}</span>
  return (
    <span className="inline-flex items-center gap-2 min-w-0">
      {avatar}
      {name}
    </span>
  )
}

export function TagList({ tags, onPick, active }) {
  if (!tags?.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((t) => (
        onPick ? (
          <button
            key={t}
            type="button"
            onClick={() => onPick(t)}
            className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
              active === t ? 'border-secondary text-secondary' : 'border-border text-text-muted hover:text-text hover:border-text-muted'
            }`}
          >
            #{t}
          </button>
        ) : (
          <Link
            key={t}
            to={`/articles?tag=${encodeURIComponent(t)}`}
            className="text-xs px-2 py-0.5 rounded-full border border-border text-text-muted hover:text-text hover:border-text-muted transition-colors"
          >
            #{t}
          </Link>
        )
      ))}
    </div>
  )
}

function Meta({ article }) {
  return (
    <span className="text-xs text-text-muted whitespace-nowrap">
      {formatArticleDate(article.published_at)}{!article.external_url && ` · ${article.reading_minutes} min read`}
    </span>
  )
}

/** Small "on eternaldurdles.com" marker for articles hosted elsewhere. */
export function ExternalBadge({ site }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold tracking-wide text-sky-300 bg-sky-400/15 px-1.5 py-0.5 rounded max-w-[12rem] truncate">
      <span aria-hidden="true">↗</span>
      <span className="truncate">{site || 'External'}</span>
    </span>
  )
}

/** The linked page's own preview image; hides itself if it fails to load. */
export function PreviewImage({ src, className = '' }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed || !(src.startsWith('https://') || src.startsWith('/card-images/'))) return null
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className={`w-full object-cover bg-bg-elevated ${className}`}
    />
  )
}

/** An article's picture. Card art is cropped to the illustration (the top
 *  part of the card) rather than the rules text. */
export function ArticleImage({ article, className = '' }) {
  const src = articleImage(article)
  const cardArt = !article.external_url && article.header_image
  return <PreviewImage src={src} className={`${cardArt ? 'object-[50%_22%]' : ''} ${className}`} />
}

/** Big tile for an article hosted on another site: its preview image,
 *  site, title, summary and a button that opens the original. */
export function LinkedArticleTile({ url, site, image, title, summary }) {
  if (!url) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer nofollow ugc"
      className="group block overflow-hidden rounded-lg border border-border bg-bg-surface hover:border-secondary/60 transition-colors"
    >
      <PreviewImage src={image} className="aspect-[1.91/1]" />
      <span className="block p-4">
        <span className="block text-xs text-text-muted truncate">{site}</span>
        {title && <span className="mt-1 block font-semibold text-text-primary group-hover:text-secondary break-words">{title}</span>}
        {summary && <span className="mt-1 block text-sm text-text-muted line-clamp-3 break-words">{summary}</span>}
        <span className="mt-3 inline-flex items-center gap-1 px-3 py-1.5 rounded-soft bg-brand-blue text-white text-sm font-medium group-hover:bg-brand-blue-light transition-colors">
          Read on {site || 'the original site'} <span aria-hidden="true">↗</span>
        </span>
      </span>
    </a>
  )
}

export function PdfBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-red-300 bg-accent-red/15 px-1.5 py-0.5 rounded">
      PDF
    </span>
  )
}

/** Card in the blog grid. The title link stretches over the whole card;
 *  tags and the author sit above it so they stay clickable. */
export function ArticleCard({ article, onTag, activeTag }) {
  const isNew = useIsNew('articles')
  return (
    <article className="group relative flex flex-col bg-bg-surface border border-border rounded-lg overflow-hidden hover:border-secondary/60 transition-colors min-w-0">
      <span className={`h-1 ${categoryColors(article.category).stripe}`} aria-hidden="true" />
      <ArticleImage article={article} className="aspect-[1.91/1] border-b border-border" />
      <div className="p-4 flex flex-col gap-2 flex-1 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          {isNew(article.published_at) && <NewTag />}
          <CategoryBadge category={article.category} />
          {article.has_pdf && <PdfBadge />}
          {article.external_url && <ExternalBadge site={article.external_site} />}
        </div>
        <h3 className="text-lg font-semibold text-text-primary leading-snug group-hover:text-secondary transition-colors break-words">
          <Link to={articlePath(article)} className="after:absolute after:inset-0 focus:outline-none focus-visible:underline">
            {article.title}
          </Link>
        </h3>
        <p className="text-sm text-text-muted line-clamp-3 break-words">{article.summary}</p>
        <div className="relative z-10 w-fit">
          <TagList tags={article.tags} onPick={onTag} active={activeTag} />
        </div>
        <div className="mt-auto pt-3 border-t border-border/60 flex items-center justify-between gap-2 text-sm">
          <span className="relative z-10 min-w-0"><AuthorChip article={article} /></span>
          <Meta article={article} />
        </div>
      </div>
    </article>
  )
}

/** Large card for the newest article at the top of the blog. */
export function FeaturedArticle({ article }) {
  const isNew = useIsNew('articles')
  return (
    <article className="group relative overflow-hidden rounded-lg border border-border bg-gradient-to-br from-brand-panel via-bg-surface to-bg-surface hover:border-secondary/60 transition-colors">
      <span className={`absolute inset-y-0 left-0 w-1 ${categoryColors(article.category).stripe}`} aria-hidden="true" />
      <div className={articleImage(article) ? 'sm:grid sm:grid-cols-[1fr_minmax(0,40%)] sm:items-center' : ''}>
      <div className="p-5 sm:p-7 pl-6 sm:pl-8 min-w-0">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-[11px] font-bold uppercase tracking-wider text-secondary">Latest article</span>
          {isNew(article.published_at) && <NewTag />}
          <CategoryBadge category={article.category} />
          {article.has_pdf && <PdfBadge />}
          {article.external_url && <ExternalBadge site={article.external_site} />}
        </div>
        <h2 className="text-2xl sm:text-3xl font-display text-text-primary group-hover:text-secondary transition-colors break-words">
          <Link to={articlePath(article)} className="after:absolute after:inset-0 focus:outline-none focus-visible:underline">
            {article.title}
          </Link>
        </h2>
        <p className="mt-2 text-text-muted max-w-3xl break-words">{article.summary}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span className="relative z-10 min-w-0"><AuthorChip article={article} size="md" /></span>
          <Meta article={article} />
        </div>
      </div>
      <ArticleImage article={article} className="aspect-[1.91/1] sm:h-full sm:aspect-auto sm:max-h-64 border-t sm:border-t-0 sm:border-l border-border" />
      </div>
    </article>
  )
}

/** Server-rendered, sanitised article HTML (see services/article_content.py). */
export function ArticleBody({ html }) {
  return <div className="article-body" dangerouslySetInnerHTML={{ __html: html || '' }} />
}
