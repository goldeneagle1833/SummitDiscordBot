import { get, post, del, ApiError } from './client'
import { ensureSiteSession, refreshSiteSession, isGateRejection } from './siteSession'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Public blog
export const listArticles = (params = {}) => {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== 0),
  ).toString()
  return get(`/api/articles${qs ? `?${qs}` : ''}`)
}
export const getArticleFacets = () => get('/api/articles/facets')
export const getArticle = (id) => get(`/api/articles/${id}`)
export const articlePdfUrl = (id) => `${API_BASE_URL}/api/articles/${id}/pdf`

// Authors
export const getMyArticles = () => get('/api/articles/mine')
export const fetchLinkPreview = (url) => post('/api/articles/link-preview', { url })
export const searchArticleCards = (q) => get(`/api/articles/card-search?q=${encodeURIComponent(q)}`)
export const cardImageUrl = (file) => (file ? `${API_BASE_URL}/card-images/${encodeURIComponent(file)}` : null)

/** The picture to show for an article: the linked page's image for an
 *  outside article, or the card the author picked as the header. */
export function articleImage(a) {
  if (!a) return null
  if (a.external_url) return a.external_image || null
  return cardImageUrl(a.header_image)
}
export const previewArticle = (body) => post('/api/articles/preview', { body })
export const deleteArticle = (id) => del(`/api/articles/${id}`)
export const addArticleComment = (id, body) => post(`/api/articles/${id}/comments`, { body })

// Create / edit send multipart form data so a PDF can ride along.
async function sendForm(url, formData) {
  await ensureSiteSession().catch(() => {})
  const send = () => fetch(`${API_BASE_URL}${url}`, { method: 'POST', credentials: 'include', body: formData })
  let res = await send()
  let data = await res.json().catch(() => ({}))
  if (!res.ok && isGateRejection(res, data)) {
    await refreshSiteSession().catch(() => {})
    res = await send()
    data = await res.json().catch(() => ({}))
  }
  if (!res.ok) throw new ApiError(res.status, data.error || res.statusText)
  return data
}

function toFormData(fields) {
  const fd = new FormData()
  Object.entries(fields).forEach(([k, v]) => {
    if (v === undefined || v === null) return
    if (k === 'tags' && Array.isArray(v)) fd.append(k, v.join(','))
    else fd.append(k, v)
  })
  return fd
}

export const submitArticle = (fields) => sendForm('/api/articles', toFormData(fields))
export const editArticle = (id, fields) => sendForm(`/api/articles/${id}/edit`, toFormData(fields))

// Reviewers
export const getReviewQueue = (status = 'pending') => get(`/api/articles/review?status=${status}`)
export const reviewArticle = (id, action, comment) =>
  post(`/api/articles/${id}/review`, { action, comment })

export const ARTICLE_CATEGORIES = [
  'Strategy',
  'Deck Guide',
  'Tournament Report',
  'Limited & Draft',
  'Lore & Art',
  'Community',
  'Other',
]

export const STATUS_LABELS = {
  pending: 'Waiting for review',
  changes_requested: 'Changes requested',
  approved: 'Published',
  rejected: 'Not approved',
}

export function articlePath(a) {
  return `/articles/${a.id}-${a.slug}`
}

export function formatArticleDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

// Reviewer list (admins only)
export const getArticleReviewers = () => get('/api/articles/reviewers')
export const addArticleReviewer = (user_id, username) => post('/api/articles/reviewers', { user_id, username })
export const removeArticleReviewer = (userId) => del(`/api/articles/reviewers/${userId}`)

// Public discussion (synced with the article's Discord thread)
export const getDiscussion = (id) => get(`/api/articles/${id}/discussion`)
export const postDiscussion = (id, body) => post(`/api/articles/${id}/discussion`, { body })
export const deleteDiscussionComment = (id, commentId) => del(`/api/articles/${id}/discussion/${commentId}`)
