import { useCallback, useEffect, useRef, useState } from 'react'
import { searchArticleCards } from '@/api/articles'
import {
  cleanHtml, formatHtml, looksLikeHtml, safeHref, safeSrc, textToHtml,
} from '@/utils/articleHtml'

// A visual (WYSIWYG) editor for articles, with an HTML view.
//
// The visual view is a contentEditable box styled like the published article.
// Pasted content keeps its formatting (cleaned to the tags articles allow), and
// HTML pasted as text (from a code view) is turned into formatted content.
// value/onChange carry HTML. The server cleans it again before saving.

const BLOCK_OPTIONS = [
  ['p', 'Paragraph'],
  ['h2', 'Heading'],
  ['h3', 'Subheading'],
  ['h4', 'Small heading'],
  ['pre', 'Code block'],
]

const inputCls = 'w-full min-w-0 bg-bg-elevated border border-border rounded px-3 py-2 text-sm focus:border-secondary/70 outline-none'

const Icon = ({ d, label }) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d.map((p) => <path key={p} d={p} />)}
    {label && <title>{label}</title>}
  </svg>
)

const ICONS = {
  ul: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.01', 'M4.5 12h.01', 'M4.5 18h.01'],
  ol: ['M10 6h10', 'M10 12h10', 'M10 18h10', 'M4 4.5h1v4', 'M3.5 8.5h2.5', 'M3.5 14.5c0-1 2.5-1 2.5 0s-2.5 2-2.5 3.5h2.5'],
  quote: ['M7 7h4v4c0 3-1.5 5-4 6', 'M14 7h4v4c0 3-1.5 5-4 6'],
  link: ['M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1.5 1.5', 'M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1.5-1.5'],
  card: ['M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M9 8h6', 'M9 12h6'],
  image: ['M4 5h16v14H4z', 'M4 16l5-5 4 4 2-2 5 5', 'M15.5 9.5h.01'],
  hr: ['M3 12h18'],
  clear: ['M4 7V5h12v2', 'M10 5l-3 14', 'M5 19h6', 'M15 14l5 5', 'M20 14l-5 5'],
  undo: ['M9 14L4 9l5-5', 'M4 9h10a6 6 0 0 1 0 12h-3'],
  redo: ['M15 14l5-5-5-5', 'M20 9H10a6 6 0 0 0 0 12h3'],
}

function ToolButton({ label, active, onRun, children, wide }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active === undefined ? undefined : active}
      // Keep the text selection: don't let the button take focus.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onRun}
      className={`shrink-0 ${wide ? 'px-2' : 'w-8 sm:w-9'} h-9 inline-flex items-center justify-center rounded text-sm transition-colors ${
        active ? 'bg-secondary/20 text-secondary' : 'text-text-primary hover:bg-white/10'
      }`}
    >
      {children}
    </button>
  )
}

const Divider = () => <span className="hidden sm:inline-block shrink-0 w-px h-6 bg-border mx-0.5" aria-hidden="true" />

export default function RichTextEditor({ value, onChange, view, placeholder, maxChars = 40000, textLength = 0 }) {
  const boxRef = useRef(null)
  const lastHtml = useRef(null)
  const savedRange = useRef(null)
  const [active, setActive] = useState({})
  const [block, setBlock] = useState('p')
  const [panel, setPanel] = useState(null) // 'link' | 'card' | 'image'
  const [panelValue, setPanelValue] = useState('')
  const [panelText, setPanelText] = useState('')
  const [panelError, setPanelError] = useState(null)
  const [cardResults, setCardResults] = useState([])
  const [source, setSource] = useState('')

  // Put outside changes (loading an article or file) into the box.
  useEffect(() => {
    if (view !== 'visual') return
    const box = boxRef.current
    // (A fresh box, after coming back from the HTML view, is always filled.)
    if (box && (value !== lastHtml.current || box.dataset.filled !== '1')) {
      box.dataset.filled = '1'
      // Always cleaned: HTML typed in the HTML view never runs in the page.
      box.innerHTML = cleanHtml(value)
      lastHtml.current = value
    }
  }, [value, view])

  useEffect(() => {
    if (view === 'html') setSource(formatHtml(cleanHtml(value)))
  }, [view]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    try { document.execCommand('defaultParagraphSeparator', false, 'p') } catch { /* old browsers */ }
  }, [])

  const emit = useCallback(() => {
    const box = boxRef.current
    if (!box) return
    const html = box.innerHTML
    lastHtml.current = html
    onChange(html)
  }, [onChange])

  const insideBox = (range) => {
    const box = boxRef.current
    return box && range && box.contains(range.commonAncestorContainer)
  }

  const refreshState = useCallback(() => {
    const sel = document.getSelection()
    if (!sel || !sel.rangeCount || !insideBox(sel.getRangeAt(0))) return
    savedRange.current = sel.getRangeAt(0).cloneRange()
    const q = (c) => { try { return document.queryCommandState(c) } catch { return false } }
    setActive({
      bold: q('bold'), italic: q('italic'), underline: q('underline'), strike: q('strikeThrough'),
      ul: q('insertUnorderedList'), ol: q('insertOrderedList'),
    })
    let tag = ''
    try { tag = String(document.queryCommandValue('formatBlock') || '').toLowerCase().replace(/[<>]/g, '') } catch { /* ignore */ }
    setBlock(tag === 'blockquote' ? 'quote' : ['h2', 'h3', 'h4', 'pre'].includes(tag) ? tag : 'p')
  }, [])

  useEffect(() => {
    document.addEventListener('selectionchange', refreshState)
    return () => document.removeEventListener('selectionchange', refreshState)
  }, [refreshState])

  const restoreSelection = () => {
    const box = boxRef.current
    if (!box) return
    box.focus({ preventScroll: true })
    const sel = document.getSelection()
    if (savedRange.current && insideBox(savedRange.current)) {
      sel.removeAllRanges()
      sel.addRange(savedRange.current)
    } else if (!sel.rangeCount || !insideBox(sel.getRangeAt(0))) {
      const r = document.createRange()
      r.selectNodeContents(box)
      r.collapse(false)
      sel.removeAllRanges()
      sel.addRange(r)
    }
  }

  const run = (command, arg = null) => {
    restoreSelection()
    document.execCommand(command, false, arg)
    emit()
    refreshState()
  }

  const insertHtml = (html) => {
    restoreSelection()
    document.execCommand('insertHTML', false, html)
    emit()
  }

  const setBlockType = (tag) => {
    if (tag === 'quote') run('formatBlock', '<blockquote>')
    else run('formatBlock', `<${tag}>`)
  }

  const openPanel = (kind) => {
    const sel = document.getSelection()
    const text = sel && sel.rangeCount && insideBox(sel.getRangeAt(0)) ? sel.toString() : ''
    if (sel && sel.rangeCount && insideBox(sel.getRangeAt(0))) savedRange.current = sel.getRangeAt(0).cloneRange()
    setPanel(kind)
    setPanelText(text)
    setPanelError(null)
    setCardResults([])
    if (kind === 'link') {
      let href = ''
      let node = sel?.anchorNode
      while (node && node !== boxRef.current) {
        if (node.nodeName === 'A') { href = node.getAttribute('href') || ''; break }
        node = node.parentNode
      }
      setPanelValue(href)
    } else {
      setPanelValue(kind === 'card' ? text.trim() : '')
    }
  }

  const closePanel = () => {
    setPanel(null)
    setPanelError(null)
    restoreSelection()
  }

  // Card name suggestions
  useEffect(() => {
    if (panel !== 'card') return undefined
    const q = panelValue.trim()
    if (q.length < 2) { setCardResults([]); return undefined }
    let live = true
    const t = setTimeout(() => {
      searchArticleCards(q)
        .then((d) => { if (live) setCardResults((d.cards || []).slice(0, 6)) })
        .catch(() => { if (live) setCardResults([]) })
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [panel, panelValue])

  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

  const applyPanel = (override) => {
    const raw = (override ?? panelValue).trim()
    if (panel === 'link') {
      if (!raw) { setPanel(null); restoreSelection(); run('unlink'); return }
      const href = safeHref(/^(https?:|mailto:|\/)/i.test(raw) ? raw : `https://${raw}`)
      if (!href) { setPanelError('Use a full web address, like https://example.com'); return }
      setPanel(null)
      if (panelText) run('createLink', href)
      else insertHtml(`<a href="${esc(href)}">${esc(raw)}</a>&nbsp;`)
    } else if (panel === 'card') {
      if (!raw) { setPanelError('Type a card name.'); return }
      setPanel(null)
      const name = raw.slice(0, 60)
      insertHtml(`<a class="card-link" href="/card/${encodeURIComponent(name)}">${esc(name)}</a>&nbsp;`)
    } else if (panel === 'image') {
      const src = safeSrc(raw)
      if (!src) { setPanelError('Paste an image link that starts with https://'); return }
      setPanel(null)
      insertHtml(`<p><img src="${esc(src)}" alt="${esc(panelText.trim())}"></p><p><br></p>`)
    }
  }

  const onPaste = (e) => {
    const html = e.clipboardData?.getData('text/html')
    const text = e.clipboardData?.getData('text/plain') || ''
    if (!html && !text) return
    e.preventDefault()
    if (html) insertHtml(cleanHtml(html))
    else if (looksLikeHtml(text)) insertHtml(cleanHtml(text))
    else if (/\n/.test(text.trim())) insertHtml(textToHtml(text))
    else { restoreSelection(); document.execCommand('insertText', false, text); emit() }
  }

  const onDrop = (e) => {
    // Dropped files would turn into huge inline images. Ask for a link instead.
    if (e.dataTransfer?.files?.length) e.preventDefault()
  }

  const onKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      openPanel('link')
    }
  }

  if (view === 'html') {
    return (
      <div>
        <textarea
          aria-label="Article HTML"
          value={source}
          onChange={(e) => { setSource(e.target.value); lastHtml.current = null; onChange(e.target.value) }}
          rows={18}
          spellCheck={false}
          className={`${inputCls} font-mono text-xs leading-relaxed`}
          placeholder={'<h2>Intro</h2>\n<p>Paste or write HTML here.</p>'}
        />
        <p className="text-xs text-text-muted mt-1">
          Allowed: paragraphs, headings, bold, italic, underline, strikethrough, lists, quotes, links,
          images (https links), tables, code and lines. Anything else (styles, scripts, frames) is removed when you save.
        </p>
      </div>
    )
  }

  const isEmpty = textLength === 0 && !/<img|<hr|<table/i.test(value || '')
  const panelLabel = { link: 'Link address', card: 'Card name', image: 'Image link (https://…)' }[panel]

  return (
    <div className="rounded border border-border bg-bg-elevated focus-within:border-secondary/70">
      <div className="sticky top-16 z-20 bg-bg-surface border-b border-border rounded-t">
        <div className="flex flex-wrap items-center gap-0.5 px-1 py-1" role="toolbar" aria-label="Formatting">
          <select
            aria-label="Text style"
            value={block}
            onMouseDown={() => refreshState()}
            onChange={(e) => setBlockType(e.target.value)}
            className="shrink-0 w-[7.5rem] sm:w-auto h-9 bg-bg-elevated border border-border rounded px-1.5 sm:px-2 text-sm mr-0.5 sm:mr-1"
          >
            {BLOCK_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            {block === 'quote' && <option value="quote">Quote</option>}
          </select>
          <ToolButton label="Bold (Ctrl+B)" active={active.bold} onRun={() => run('bold')}><b className="font-bold">B</b></ToolButton>
          <ToolButton label="Italic (Ctrl+I)" active={active.italic} onRun={() => run('italic')}><i className="font-serif italic">I</i></ToolButton>
          <ToolButton label="Underline (Ctrl+U)" active={active.underline} onRun={() => run('underline')}><span className="underline">U</span></ToolButton>
          <ToolButton label="Strikethrough" active={active.strike} onRun={() => run('strikeThrough')}><span className="line-through">S</span></ToolButton>
          <Divider />
          <ToolButton label="Bulleted list" active={active.ul} onRun={() => run('insertUnorderedList')}><Icon d={ICONS.ul} /></ToolButton>
          <ToolButton label="Numbered list" active={active.ol} onRun={() => run('insertOrderedList')}><Icon d={ICONS.ol} /></ToolButton>
          <ToolButton label="Quote" active={block === 'quote'} onRun={() => setBlockType(block === 'quote' ? 'p' : 'quote')}><Icon d={ICONS.quote} /></ToolButton>
          <Divider />
          <ToolButton label="Link (Ctrl+K)" active={panel === 'link'} onRun={() => (panel === 'link' ? closePanel() : openPanel('link'))}><Icon d={ICONS.link} /></ToolButton>
          <ToolButton label="Card link" active={panel === 'card'} onRun={() => (panel === 'card' ? closePanel() : openPanel('card'))}><Icon d={ICONS.card} /></ToolButton>
          <ToolButton label="Image" active={panel === 'image'} onRun={() => (panel === 'image' ? closePanel() : openPanel('image'))}><Icon d={ICONS.image} /></ToolButton>
          <ToolButton label="Horizontal line" onRun={() => run('insertHorizontalRule')}><Icon d={ICONS.hr} /></ToolButton>
          <Divider />
          <ToolButton label="Clear formatting" onRun={() => { run('removeFormat'); run('unlink') }}><Icon d={ICONS.clear} /></ToolButton>
          <ToolButton label="Undo" onRun={() => run('undo')}><Icon d={ICONS.undo} /></ToolButton>
          <ToolButton label="Redo" onRun={() => run('redo')}><Icon d={ICONS.redo} /></ToolButton>
        </div>

        {panel && (
          <div className="border-t border-border px-2 py-2 space-y-1">
            <form
              className="flex flex-wrap sm:flex-nowrap items-center gap-2"
              onSubmit={(e) => { e.preventDefault(); e.stopPropagation(); applyPanel() }}
            >
              <input
                autoFocus
                aria-label={panelLabel}
                value={panelValue}
                onChange={(e) => { setPanelValue(e.target.value); setPanelError(null) }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') { e.preventDefault(); closePanel() }
                  if (e.key === 'Enter') { e.preventDefault(); applyPanel() }
                }}
                inputMode={panel === 'card' ? 'text' : 'url'}
                placeholder={panelLabel}
                className={`${inputCls} flex-1 basis-full sm:basis-auto`}
              />
              {panel === 'image' && (
                <input
                  aria-label="Image description"
                  value={panelText}
                  onChange={(e) => setPanelText(e.target.value)}
                  placeholder="Description (optional)"
                  className={`${inputCls} flex-1 basis-full sm:basis-auto`}
                />
              )}
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => applyPanel()} className="px-3 py-2 text-sm rounded bg-brand-blue text-white hover:bg-brand-blue-light">
                {panel === 'link' && !panelValue.trim() ? 'Remove link' : panel === 'link' ? 'Add link' : 'Insert'}
              </button>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={closePanel} className="px-3 py-2 text-sm rounded border border-border hover:border-text-muted">
                Cancel
              </button>
            </form>
            {panelError && <p className="text-xs text-red-300">{panelError}</p>}
            {panel === 'card' && cardResults.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {cardResults.map((c) => (
                  <button
                    key={c.name}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => applyPanel(c.name)}
                    className="px-2 py-1 text-xs rounded-full border border-border hover:border-secondary text-text-primary"
                  >
                    {c.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="relative">
        {isEmpty && (
          <div className="absolute inset-x-0 top-0 px-4 py-3 text-text-muted pointer-events-none select-none article-body" aria-hidden="true">
            {placeholder}
          </div>
        )}
        <div
          ref={boxRef}
          role="textbox"
          aria-multiline="true"
          aria-label="Article text"
          contentEditable
          suppressContentEditableWarning
          spellCheck
          onInput={emit}
          onBlur={emit}
          onPaste={onPaste}
          onDrop={onDrop}
          onKeyDown={onKeyDown}
          onKeyUp={refreshState}
          onMouseUp={refreshState}
          className="article-body article-editor min-h-[22rem] px-4 py-3 outline-none break-words"
        />
      </div>
      <div className="flex justify-end px-3 py-1 border-t border-border text-xs text-text-muted">
        <span className={textLength > maxChars ? 'text-red-300' : ''}>{textLength.toLocaleString()}/{maxChars.toLocaleString()} characters</span>
      </div>
    </div>
  )
}
