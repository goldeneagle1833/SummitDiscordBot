// Cleans HTML for the article editor (pasted content, the HTML source view and
// loaded files) down to the tags articles allow. The server cleans everything
// again before saving (services/article_content.sanitize_html); this copy just
// keeps the editor showing what will actually be published.

const KEEP = new Set([
  'p', 'br', 'h2', 'h3', 'h4', 'strong', 'em', 'u', 's', 'sub', 'sup',
  'blockquote', 'ul', 'ol', 'li', 'a', 'code', 'pre', 'hr', 'img',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'figure', 'figcaption',
])
const RENAME = {
  b: 'strong', i: 'em', strike: 's', del: 's', ins: 'u',
  h1: 'h2', h5: 'h4', h6: 'h4', tfoot: 'tbody', kbd: 'code', tt: 'code', samp: 'code',
  div: 'p', section: 'p', article: 'p', header: 'p', footer: 'p', main: 'p',
  aside: 'p', address: 'p', center: 'p', dd: 'p', dt: 'p', caption: 'p',
}
const DROP = new Set([
  'script', 'style', 'iframe', 'frameset', 'object', 'applet',
  'noscript', 'noembed', 'noframes', 'template', 'svg', 'math', 'head', 'title',
  'textarea', 'select', 'button', 'form', 'audio', 'video', 'canvas',
  'map',
])
const VOID = new Set(['br', 'hr', 'img'])
const LINK_ATTRS = 'target="_blank" rel="nofollow ugc noopener noreferrer"'

const esc = (s) => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export function safeHref(raw) {
  const href = String(raw || '').replace(/[\u0000- \u007f]/g, '')
  if (!href || href.length > 500) return null
  if (href.startsWith('/card/') && !href.includes('//')) return href
  if (/^https?:\/\/[^/\s]+/i.test(href)) return href
  if (/^mailto:[^\s@]+@[^\s@]+$/i.test(href)) return href
  return null
}

export function safeSrc(raw) {
  const src = String(raw || '').replace(/[\u0000- \u007f]/g, '')
  if (!src || src.length > 1000) return null
  if (/^https:\/\/[^/\s]+/i.test(src)) return src
  if (src.startsWith('/card-images/') && !src.includes('//') && !src.includes('..')) return src
  return null
}

/** Is a piece of plain text really HTML markup (pasted from a code view)? */
export function looksLikeHtml(text) {
  return /<\/?(p|h[1-6]|div|br|strong|em|b|i|u|ul|ol|li|a|img|table|tr|td|blockquote|pre|code|span|hr)\b[^>]*>/i.test(text || '')
}

function walk(node, out, ctx) {
  for (const child of Array.from(node.childNodes)) {
    if (child.nodeType === 3) {
      const text = child.nodeValue.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '')
      if (ctx.pre) { out.push(esc(text)); continue }
      // Line breaks between blocks in HTML source aren't content (the editor
      // would show them as blank lines). Inside a line they're just spaces.
      if (/^\s*$/.test(text) && /\n/.test(text)) continue
      const flat = text.replace(/\s*\n\s*/g, ' ')
      if (ctx.inLink || ctx.code) { out.push(esc(flat)); continue }
      // [[Card Name]] becomes a card link, as it will when published.
      let pos = 0
      for (const m of flat.matchAll(/\[\[([^[\]\n|]{1,60})\]\]/g)) {
        out.push(esc(flat.slice(pos, m.index)))
        const name = m[1].trim()
        out.push(`<a class="card-link" href="/card/${esc(encodeURIComponent(name))}">${esc(name)}</a>`)
        pos = m.index + m[0].length
      }
      out.push(esc(flat.slice(pos)))
      continue
    }
    if (child.nodeType !== 1) continue
    const tag = child.tagName.toLowerCase()
    if (DROP.has(tag)) continue
    // Google Docs wraps everything in <b style="font-weight:normal">
    let name = RENAME[tag] || tag
    if (name === 'strong' && /font-weight:\s*(normal|400)/i.test(child.getAttribute('style') || '')) name = 'span'
    if (name === 'p' && ctx.inline) name = 'span'
    // Google Docs puts a <p> in every list item; that just adds big gaps.
    if (name === 'p' && ctx.parent === 'li') {
      walk(child, out, ctx)
      let next = child.nextSibling
      while (next && next.nodeType === 3 && !next.nodeValue.trim()) next = next.nextSibling
      if (next) out.push('<br>')
      continue
    }
    if (!KEEP.has(name)) {
      walk(child, out, ctx)
      continue
    }
    if (name === 'a') {
      const href = safeHref(child.getAttribute('href'))
      if (!href || ctx.inLink) { walk(child, out, ctx); continue }
      out.push(href.startsWith('/card/')
        ? `<a class="card-link" href="${esc(href)}">`
        : `<a href="${esc(href)}" ${LINK_ATTRS}>`)
      walk(child, out, { ...ctx, inLink: true })
      out.push('</a>')
      continue
    }
    if (name === 'img') {
      const src = safeSrc(child.getAttribute('src'))
      if (src) out.push(`<img src="${esc(src)}" alt="${esc((child.getAttribute('alt') || '').slice(0, 200))}" loading="lazy" referrerpolicy="no-referrer">`)
      continue
    }
    let attrs = ''
    if (name === 'td' || name === 'th') {
      for (const k of ['colspan', 'rowspan']) {
        const n = parseInt(child.getAttribute(k), 10)
        if (n >= 2 && n <= 20) attrs += ` ${k}="${n}"`
      }
    }
    if (name === 'ol') {
      const n = parseInt(child.getAttribute('start'), 10)
      if (Number.isFinite(n) && n !== 1 && n >= 0 && n < 10000) attrs += ` start="${n}"`
    }
    if (VOID.has(name)) { out.push(`<${name}>`); continue }
    out.push(`<${name}${attrs}>`)
    walk(child, out, {
      ...ctx,
      pre: ctx.pre || name === 'pre',
      code: ctx.code || name === 'code',
      parent: name,
      // A <div> inside a paragraph or heading can't become another paragraph.
      inline: ctx.inline || name === 'p' || /^h[2-4]$/.test(name),
    })
    out.push(`</${name}>`)
  }
}

/** Clean HTML down to the allowed tags. Returns a string of safe HTML. */
export function cleanHtml(html) {
  if (!html) return ''
  const doc = new DOMParser().parseFromString(String(html), 'text/html')
  const out = []
  walk(doc.body, out, { pre: false, code: false, inline: false, inLink: false })
  let result = out.join('')
  // Empty paragraphs and headings (but keep one blank line's worth of <br>)
  let prev
  do {
    prev = result
    result = result.replace(/<(p|h2|h3|h4|li|blockquote)>(?:\s|&nbsp;| )*<\/\1>/g, '')
  } while (prev !== result)
  return result.trim()
}

/** Plain text (as typed or pasted) to paragraphs of HTML. */
export function textToHtml(text) {
  return String(text || '')
    .replace(/\r\n?/g, '\n')
    .split(/\n{2,}/)
    .map((para) => para.trim())
    .filter(Boolean)
    .map((para) => `<p>${esc(para).replace(/\n/g, '<br>')}</p>`)
    .join('')
}

/** HTML laid out one block per line, for the HTML view. */
export function formatHtml(html) {
  return String(html || '')
    .replace(/\s*(<\/(?:p|h2|h3|h4|blockquote|ul|ol|li|pre|table|thead|tbody|tr|figure)>|<hr>)\s*/g, '$1\n')
    .replace(/(<(?:ul|ol|table|thead|tbody|tr|blockquote|figure)(?: [^>]*)?>)\s*/g, '$1\n')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

/** Characters of text a reader sees. */
export function htmlTextLength(html) {
  if (!html) return 0
  const doc = new DOMParser().parseFromString(String(html), 'text/html')
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim().length
}

