// Plain text with http(s) and www. links turned into clickable links.
// Punctuation that ends a sentence stays outside the link.
const URL_RE = /(https?:\/\/[^\s<]+|www\.[^\s<]+)/gi
const TRAILING_RE = /[.,!?;:)\]'"]+$/

export default function LinkifiedText({ text, linkClassName = 'text-secondary hover:underline' }) {
  if (!text) return null
  const out = []
  let last = 0
  for (const match of text.matchAll(URL_RE)) {
    let url = match[0]
    const trailing = url.match(TRAILING_RE)?.[0] || ''
    url = url.slice(0, url.length - trailing.length)
    if (match.index > last) out.push(text.slice(last, match.index))
    const href = /^https?:\/\//i.test(url) ? url : `https://${url}`
    out.push(
      <a key={match.index} href={href} target="_blank" rel="noopener noreferrer" className={linkClassName}>
        {url}
      </a>,
    )
    last = match.index + url.length
  }
  if (last < text.length) out.push(text.slice(last))
  return <>{out}</>
}
