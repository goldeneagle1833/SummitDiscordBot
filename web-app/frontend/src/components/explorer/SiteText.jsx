import LinkifiedText from '@/components/ui/LinkifiedText'

/**
 * Renders the text Explorer admins write for their site. A small, safe subset
 * of Markdown, built as React elements (never raw HTML):
 *   blank line   new paragraph
 *   ## Heading   subheading
 *   - item       bullet list
 *   **bold**     bold
 *   [text](url)  link (http/https only); bare links work too
 */
const INLINE_RE = /(\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g

function Inline({ text }) {
  const parts = []
  let last = 0
  for (const m of text.matchAll(INLINE_RE)) {
    if (m.index > last) parts.push(<LinkifiedText key={`t${last}`} text={text.slice(last, m.index)} linkClassName="es-link underline" />)
    const token = m[0]
    if (token.startsWith('**')) {
      parts.push(<strong key={m.index}>{token.slice(2, -2)}</strong>)
    } else {
      const [, label, href] = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/)
      parts.push(<a key={m.index} href={href} target="_blank" rel="noopener noreferrer" className="es-link underline">{label}</a>)
    }
    last = m.index + token.length
  }
  if (last < text.length) parts.push(<LinkifiedText key={`t${last}`} text={text.slice(last)} linkClassName="es-link underline" />)
  return <>{parts}</>
}

export default function SiteText({ text, className = '' }) {
  if (!text) return null
  const blocks = []
  let list = null
  let para = []
  const flushPara = () => {
    if (para.length) blocks.push({ type: 'p', lines: para })
    para = []
  }
  const flushList = () => {
    if (list) blocks.push({ type: 'ul', items: list })
    list = null
  }
  for (const raw of text.split('\n')) {
    const line = raw.trimEnd()
    if (!line.trim()) { flushPara(); flushList(); continue }
    if (/^\s*[-*•]\s+/.test(line)) {
      flushPara()
      list = list || []
      list.push(line.replace(/^\s*[-*•]\s+/, ''))
      continue
    }
    flushList()
    if (/^#{1,3}\s+/.test(line)) {
      flushPara()
      blocks.push({ type: 'h', text: line.replace(/^#{1,3}\s+/, '') })
      continue
    }
    para.push(line)
  }
  flushPara()
  flushList()

  return (
    <div className={`space-y-3 leading-relaxed ${className}`}>
      {blocks.map((b, i) => {
        if (b.type === 'h') return <h3 key={i} className="es-heading text-lg font-bold pt-1">{b.text}</h3>
        if (b.type === 'ul') {
          return (
            <ul key={i} className="list-disc pl-5 space-y-1">
              {b.items.map((item, j) => <li key={j}><Inline text={item} /></li>)}
            </ul>
          )
        }
        return (
          <p key={i}>
            {b.lines.map((l, j) => <span key={j}>{j > 0 && <br />}<Inline text={l} /></span>)}
          </p>
        )
      })}
    </div>
  )
}
