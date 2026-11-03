import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ARTICLE_CATEGORIES, editArticle, fetchLinkPreview, getArticle, previewArticle, submitArticle,
} from '@/api/articles'
import { ArticleBody, LinkedArticleTile, StatusBadge } from '@/components/articles/ArticleBits'
import Spinner from '@/components/ui/Spinner'
import usePageTitle from '@/hooks/usePageTitle'

const PDF_MAX = 10 * 1024 * 1024
const TEXT_FILE_MAX = 200 * 1024
const inputCls = 'w-full bg-bg-elevated border border-border rounded px-3 py-2 text-sm focus:border-secondary/70 outline-none'

export default function ArticleEditor() {
  const { id } = useParams()
  const editing = Boolean(id)
  usePageTitle(editing ? 'Edit article' : 'Write an article')
  const navigate = useNavigate()

  const [loaded, setLoaded] = useState(!editing)
  const [existing, setExisting] = useState(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('')
  const [tags, setTags] = useState('')
  const [summary, setSummary] = useState('')
  const [body, setBody] = useState('')
  const [pdf, setPdf] = useState(null)
  const [removePdf, setRemovePdf] = useState(false)
  // 'write' = written here; 'link' = an article hosted on another site
  const [mode, setMode] = useState('write')
  const [linkUrl, setLinkUrl] = useState('')
  const [linkCard, setLinkCard] = useState(null)
  const [linkBusy, setLinkBusy] = useState(false)
  const [linkMsg, setLinkMsg] = useState(null)
  const [tab, setTab] = useState('write')
  const [preview, setPreview] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const textFileRef = useRef(null)
  const pdfRef = useRef(null)

  useEffect(() => {
    if (!editing) return
    getArticle(id)
      .then((a) => {
        if (!a.can_edit) throw new Error('You can only edit your own articles.')
        setExisting(a)
        setTitle(a.title)
        setCategory(a.category)
        setTags((a.tags || []).join(', '))
        setSummary(a.summary)
        setBody(a.body_md || '')
        if (a.external_url) {
          setMode('link')
          setLinkUrl(a.external_url)
          setLinkCard({ url: a.external_url, site: a.external_site, image: a.external_image })
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoaded(true))
  }, [editing, id])

  useEffect(() => {
    if (tab !== 'preview') return
    setPreview(null)
    previewArticle(body).then(setPreview).catch((e) => setPreview({ html: '', error: e.message }))
  }, [tab, body])

  const loadTextFile = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!/\.(txt|md|markdown)$/i.test(file.name)) {
      setError('Pick a .txt or .md file. For Word or Google Docs, copy and paste the text in.')
      return
    }
    if (file.size > TEXT_FILE_MAX) {
      setError('That text file is too big (200 KB max).')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setBody(String(reader.result || ''))
      if (!title) setTitle(file.name.replace(/\.(txt|md|markdown)$/i, '').replace(/[-_]+/g, ' '))
      setError(null)
    }
    reader.readAsText(file)
  }

  const pickPdf = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf')) {
      setError('Only PDF files can be attached.')
      return
    }
    if (file.size > PDF_MAX) {
      setError('PDFs can be up to 10 MB.')
      return
    }
    setPdf(file)
    setRemovePdf(false)
    setError(null)
  }

  const getLinkPreview = async (pasted) => {
    const target = (typeof pasted === 'string' ? pasted : linkUrl).trim()
    if (!target) return
    setLinkBusy(true)
    setLinkMsg(null)
    try {
      const p = await fetchLinkPreview(target)
      setLinkUrl(p.url)
      setLinkCard(p)
      if (p.found) {
        if (!title.trim() && p.title) setTitle(p.title)
        if (!summary.trim() && p.summary) setSummary(p.summary)
      } else {
        setLinkMsg("We couldn't read a preview from that page. You can still send it; fill in the title and summary yourself.")
      }
    } catch (err) {
      setLinkCard(null)
      setLinkMsg(err.message)
    } finally {
      setLinkBusy(false)
    }
  }

  const switchMode = (m) => {
    setMode(m)
    setError(null)
    if (m === 'link') {
      setPdf(null)
      setRemovePdf(Boolean(existing?.has_pdf))
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    const linking = mode === 'link'
    const fields = {
      title, category, tags, summary, body,
      external_url: linking ? linkUrl.trim() : '',
      pdf: !linking && pdf ? pdf : undefined,
      remove_pdf: removePdf || (linking && existing?.has_pdf) ? '1' : undefined,
    }
    try {
      const res = editing ? await editArticle(id, fields) : await submitArticle(fields)
      navigate(`/articles/mine?id=${res.id}&sent=1`)
    } catch (err) {
      setError(err.message)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <Spinner className="py-20" />
  if (editing && !existing) {
    return (
      <div className="max-w-3xl mx-auto text-center py-16">
        <p>{error || 'Article not found'}</p>
        <Link to="/articles/mine" className="text-secondary text-sm hover:underline">My articles</Link>
      </div>
    )
  }

  const hasPdf = Boolean(pdf) || (existing?.has_pdf && !removePdf)

  return (
    <div className="max-w-6xl mx-auto">
      <Link to={editing ? '/articles/mine' : '/articles'} className="text-sm text-text-muted hover:text-secondary">
        ← {editing ? 'My articles' : 'All articles'}
      </Link>
      <div className="flex flex-wrap items-center gap-3 mt-2 mb-5">
        <h1 className="text-2xl font-display text-secondary">{editing ? 'Edit article' : 'Write an article'}</h1>
        {existing && <StatusBadge status={existing.status} />}
      </div>

      {editing && existing?.status === 'approved' && (
        <p className="mb-4 text-sm rounded-lg border border-secondary/40 bg-secondary/5 px-3 py-2">
          This article is live. Saving changes takes it down until a reviewer approves the new version.
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-sm rounded-lg border border-accent-red/50 bg-accent-red/10 text-red-300 px-3 py-2">{error}</p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        <form onSubmit={submit} className="space-y-4 min-w-0">
          <fieldset>
            <legend className="block text-xs text-text-muted mb-1">What are you sharing?</legend>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                ['write', 'Write it here', 'Your article lives on Summit.'],
                ['link', 'Link an article', 'Share an article hosted on another site.'],
              ].map(([m, label, hint]) => (
                <label
                  key={m}
                  className={`flex items-start gap-2 rounded-lg border p-3 cursor-pointer transition-colors ${
                    mode === m ? 'border-secondary bg-secondary/5' : 'border-border bg-bg-surface hover:border-text-muted'
                  }`}
                >
                  <input type="radio" name="a-mode" value={m} checked={mode === m} onChange={() => switchMode(m)} className="mt-1 accent-secondary" />
                  <span>
                    <span className="block text-sm font-semibold text-text-primary">{label}</span>
                    <span className="block text-xs text-text-muted">{hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {mode === 'link' && (
            <div className="rounded-lg border border-border bg-bg-surface p-3 space-y-3">
              <div>
                <label htmlFor="a-link" className="block text-xs text-text-muted mb-1">Link to the article</label>
                <div className="flex gap-2">
                  <input
                    id="a-link"
                    type="text"
                    inputMode="url"
                    value={linkUrl}
                    onChange={(e) => { setLinkUrl(e.target.value); setLinkCard(null); setLinkMsg(null) }}
                    onPaste={(e) => { const t = e.clipboardData?.getData('text'); if (t) setTimeout(() => getLinkPreview(t), 0) }}
                    maxLength={500}
                    required
                    className={inputCls}
                    placeholder="https://…"
                  />
                  <button
                    type="button"
                    onClick={() => getLinkPreview()}
                    disabled={linkBusy || !linkUrl.trim()}
                    className="shrink-0 px-3 py-2 text-sm rounded border border-border hover:border-secondary disabled:opacity-40 transition-colors"
                  >
                    {linkBusy ? 'Checking…' : 'Get preview'}
                  </button>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  We read the page's preview card (title, summary, image) and fill in the fields below. You can change them.
                </p>
              </div>
              {linkMsg && <p className="text-xs text-secondary">{linkMsg}</p>}
              {linkCard && (
                <div className="max-w-md">
                  <p className="text-xs text-text-muted mb-1">How the link tile will look</p>
                  <LinkedArticleTile
                    url={linkCard.url}
                    site={linkCard.site}
                    image={linkCard.image}
                    title={title || linkCard.title}
                    summary={summary || linkCard.summary}
                  />
                </div>
              )}
            </div>
          )}

          <div>
            <label htmlFor="a-title" className="block text-xs text-text-muted mb-1">Title</label>
            <input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required className={`${inputCls} text-base`} placeholder="e.g. Piloting Frogs in Season 8" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="a-category" className="block text-xs text-text-muted mb-1">Category</label>
              <select id="a-category" value={category} onChange={(e) => setCategory(e.target.value)} required className={inputCls}>
                <option value="">Pick one…</option>
                {ARTICLE_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="a-tags" className="block text-xs text-text-muted mb-1">Tags (up to 5, comma separated)</label>
              <input id="a-tags" value={tags} onChange={(e) => setTags(e.target.value)} maxLength={150} className={inputCls} placeholder="frogs, tempo, season 8" />
            </div>
          </div>
          <div>
            <label htmlFor="a-summary" className="flex justify-between text-xs text-text-muted mb-1">
              <span>Summary (shown on the blog card)</span>
              <span>{summary.length}/300</span>
            </label>
            <textarea id="a-summary" value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={300} rows={2} required className={`${inputCls} resize-none`} />
          </div>

          {mode === 'link' ? (
            <div>
              <label htmlFor="a-note" className="flex justify-between text-xs text-text-muted mb-1">
                <span>Note (optional): why it's worth a read</span>
                <span>{body.length.toLocaleString()}/40,000</span>
              </label>
              <textarea id="a-note" value={body} onChange={(e) => setBody(e.target.value)} maxLength={40000} rows={5} className={inputCls} />
            </div>
          ) : (
          <div>
            <div className="flex flex-wrap items-end justify-between gap-2 mb-1">
              <div className="inline-flex gap-1 bg-bg-surface border border-border rounded-full p-1" role="tablist">
                {['write', 'preview'].map((t) => (
                  <button
                    key={t}
                    type="button"
                    role="tab"
                    aria-selected={tab === t}
                    onClick={() => setTab(t)}
                    className={`px-3 py-1 rounded-full text-sm font-semibold capitalize ${tab === t ? 'bg-bg-elevated text-secondary' : 'text-text-muted hover:text-text'}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="text-text-muted">{body.length.toLocaleString()}/40,000</span>
                <button type="button" onClick={() => textFileRef.current?.click()} className="text-secondary hover:underline">
                  Load a .txt / .md file
                </button>
                <input ref={textFileRef} type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" className="hidden" onChange={loadTextFile} />
              </div>
            </div>
            {tab === 'write' ? (
              <textarea
                aria-label="Article text"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                maxLength={40000}
                rows={18}
                className={`${inputCls} font-mono leading-relaxed`}
                placeholder={'## Intro\nWrite your article here. Use **bold**, *italics*, lists, links and [[Card Name]] for card links.'}
              />
            ) : (
              <div className="min-h-[20rem] bg-bg-surface border border-border rounded p-4">
                {preview === null ? <Spinner className="py-10" /> : preview.html ? <ArticleBody html={preview.html} /> : (
                  <p className="text-sm text-text-muted">{preview.error || 'Nothing to preview yet.'}</p>
                )}
              </div>
            )}
          </div>

          )}

          {mode === 'write' && (
          <div className="rounded-lg border border-dashed border-border p-3">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-medium">PDF version <span className="text-text-muted font-normal">(optional, 10 MB max)</span></span>
              <button type="button" onClick={() => pdfRef.current?.click()} className="px-3 py-1 text-sm rounded border border-border hover:border-secondary transition-colors">
                {hasPdf ? 'Replace PDF' : 'Attach PDF'}
              </button>
              <input ref={pdfRef} type="file" accept="application/pdf,.pdf" className="hidden" onChange={pickPdf} />
              {pdf && <span className="text-sm text-text-muted truncate max-w-full">{pdf.name}</span>}
              {!pdf && existing?.has_pdf && !removePdf && (
                <span className="text-sm text-text-muted truncate">{existing.pdf_original_name || 'Attached PDF'}</span>
              )}
              {hasPdf && (
                <button type="button" onClick={() => { setPdf(null); setRemovePdf(Boolean(existing?.has_pdf)) }} className="text-xs text-red-400 hover:underline">
                  Remove
                </button>
              )}
            </div>
            <p className="text-xs text-text-muted mt-1">
              With a PDF attached the text above can be short. PDFs with scripts, attachments or passwords are refused.
            </p>
          </div>
          )}

          <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
            <span className="text-xs text-text-muted">A reviewer reads it before it goes live.</span>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 rounded-soft bg-brand-blue text-white hover:bg-brand-blue-light font-medium disabled:opacity-40 transition-colors"
            >
              {saving ? 'Sending…' : editing ? 'Save and send for review' : 'Send for review'}
            </button>
          </div>
        </form>

        <aside className="space-y-4 text-sm min-w-0 lg:order-none order-first">
          <div className="bg-bg-surface border border-border rounded-lg p-4">
            <h2 className="font-semibold text-text-primary mb-2">What we publish</h2>
            <ul className="list-disc pl-4 space-y-1 text-text-muted">
              <li>Your own writing about Sorcery: strategy, decks, events, lore and art.</li>
              <li>Respectful and on topic. No ads, spam or personal attacks.</li>
              <li>Credit art and quotes that aren't yours.</li>
            </ul>
            <p className="text-text-muted mt-2">A reviewer may comment or ask for changes. You'll get a Discord DM if you logged in with Discord, and comments always show on My articles.</p>
          </div>
          <div className="bg-bg-surface border border-border rounded-lg p-4 hidden lg:block">
            <h2 className="font-semibold text-text-primary mb-2">Formatting</h2>
            <dl className="space-y-1 text-text-muted font-mono text-xs">
              <div><dt className="inline">## Heading</dt></div>
              <div><dt className="inline">**bold**  *italic*</dt></div>
              <div><dt className="inline">- list item</dt></div>
              <div><dt className="inline">1. numbered item</dt></div>
              <div><dt className="inline">&gt; quote</dt></div>
              <div><dt className="inline">[text](https://…)</dt></div>
              <div><dt className="inline">[[Card Name]]</dt> <dd className="inline font-sans">links the card</dd></div>
            </dl>
          </div>
        </aside>
      </div>
    </div>
  )
}
