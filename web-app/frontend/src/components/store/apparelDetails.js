// Turns a Shopify product description (HTML written in the Explorer team's
// Shopify admin) into plain, safe sections for the Apparel cards.

const ALLOWED = new Set([
  'P', 'UL', 'OL', 'LI', 'STRONG', 'B', 'EM', 'I', 'BR', 'SPAN', 'DIV',
  'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
])
const DROP = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'TEMPLATE', 'NOSCRIPT', 'SVG', 'MATH', 'IMG', 'VIDEO', 'AUDIO', 'FORM', 'INPUT', 'BUTTON', 'TEXTAREA', 'SELECT', 'LINK', 'META'])

// Keeps only plain formatting tags with no attributes at all, so nothing in
// the description can run code, load anything or restyle our page
function clean(source, doc) {
  const out = doc.createDocumentFragment()
  source.childNodes.forEach((child) => {
    if (child.nodeType === 3) {
      out.appendChild(doc.createTextNode(child.textContent))
    } else if (child.nodeType === 1) {
      if (DROP.has(child.tagName)) return
      const inner = clean(child, doc)
      if (ALLOWED.has(child.tagName)) {
        const el = doc.createElement(child.tagName.toLowerCase())
        el.appendChild(inner)
        out.appendChild(el)
      } else {
        out.appendChild(inner) // unknown tags (links included) keep just their text
      }
    }
  })
  return out
}

const SIZE_HEADING = /measurement|size chart|sizing/i
const isSizeHeading = (el) => el.textContent.trim().length < 60 && SIZE_HEADING.test(el.textContent)

// Returns { details, sizeChart } as safe HTML strings (either may be '').
// The size chart starts at the first short "measurements"/"size chart"
// heading, or at the first table when there's no such heading.
export function splitDescription(html) {
  if (!html || typeof DOMParser === 'undefined') return { details: '', sizeChart: '' }
  const parsed = new DOMParser().parseFromString(html, 'text/html')
  const doc = document.implementation.createHTMLDocument('')
  doc.body.appendChild(clean(parsed.body, doc))

  const all = Array.from(doc.body.querySelectorAll('*'))
  // The innermost short element naming the size chart, or the first table
  const heading = all.find((el) => isSizeHeading(el) && !Array.from(el.children).some(isSizeHeading))
  const start = heading || doc.body.querySelector('table')

  let details = doc.body.innerHTML
  let sizeChart = ''
  if (start) {
    // Everything before the start point is the details; the range split keeps
    // both halves' lists and wrappers intact
    const range = doc.createRange()
    range.setStart(doc.body, 0)
    range.setEndBefore(start)
    const holder = doc.createElement('div')
    holder.appendChild(range.extractContents())
    if (heading) heading.remove() // the section's own title says "Size chart"
    details = holder.innerHTML
    sizeChart = doc.body.innerHTML
  }
  const hasText = (h) => {
    const d = doc.createElement('div')
    d.innerHTML = h
    return d.textContent.trim().length > 0
  }
  // Lists cut in two leave empty items behind
  const tidy = (h) => {
    const d = doc.createElement('div')
    d.innerHTML = h
    d.querySelectorAll('li, p, div, ul, ol').forEach((el) => {
      if (!el.textContent.trim() && !el.querySelector('table, br')) el.remove()
    })
    return d.innerHTML
  }
  details = tidy(details)
  sizeChart = tidy(sizeChart)
  return { details: hasText(details) ? details : '', sizeChart: hasText(sizeChart) ? sizeChart : '' }
}
