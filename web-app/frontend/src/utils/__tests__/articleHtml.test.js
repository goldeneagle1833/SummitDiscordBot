import { describe, expect, it } from 'vitest'
import { cleanHtml, formatHtml, htmlTextLength, looksLikeHtml, safeHref, textToHtml } from '../articleHtml'

describe('cleanHtml', () => {
  it('drops scripts, handlers and styles', () => {
    const out = cleanHtml('<p style="color:red" onclick="x()">Hi <script>alert(1)</script><img src=x onerror=alert(1)></p>')
    expect(out).toBe('<p>Hi </p>')
  })

  it('keeps formatting and renames old tags', () => {
    expect(cleanHtml('<h1>T</h1><b>b</b> <i>i</i> <strike>s</strike>'))
      .toBe('<h2>T</h2><strong>b</strong> <em>i</em> <s>s</s>')
  })

  it('unwraps the Google Docs bold wrapper and spans', () => {
    const docs = '<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1"><p dir="ltr"><span style="font-size:11pt">Hello</span></p></b>'
    expect(cleanHtml(docs)).toBe('<p>Hello</p>')
  })

  it('only keeps safe links and https images', () => {
    expect(cleanHtml('<a href="javascript:alert(1)">x</a>')).toBe('x')
    expect(cleanHtml('<a href="https://a.com">a</a>')).toContain('href="https://a.com" target="_blank"')
    expect(cleanHtml('<a href="/card/Frog">Frog</a>')).toBe('<a class="card-link" href="/card/Frog">Frog</a>')
    expect(cleanHtml('<img src="http://a.com/x.png">')).toBe('')
    expect(cleanHtml('<img src="https://a.com/x.png" alt="x">')).toContain('src="https://a.com/x.png"')
  })

  it('does not nest paragraphs from divs', () => {
    expect(cleanHtml('<p>a<div>b</div></p>')).not.toContain('<p><p>')
  })
})

describe('helpers', () => {
  it('spots HTML pasted as text', () => {
    expect(looksLikeHtml('<p>Hello</p>')).toBe(true)
    expect(looksLikeHtml('a < b and c > d')).toBe(false)
  })
  it('turns plain text into paragraphs', () => {
    expect(textToHtml('one\ntwo\n\nthree <x>')).toBe('<p>one<br>two</p><p>three &lt;x&gt;</p>')
  })
  it('lays out blocks one per line', () => {
    expect(formatHtml('<p>a</p><ul><li>b</li></ul>')).toBe('<p>a</p>\n<ul>\n<li>b</li>\n</ul>')
  })
  it('counts reader-visible characters', () => {
    expect(htmlTextLength('<p><strong>ab</strong>  c</p>')).toBe(4)
  })
  it('rejects bad hrefs', () => {
    expect(safeHref(' java\tscript:alert(1)')).toBe(null)
    expect(safeHref('//evil.com')).toBe(null)
  })
})

describe('editor paste details', () => {
  it('drops newlines between blocks and links [[cards]]', () => {
    expect(cleanHtml('<p>a</p>\n  <p>Play [[Pudge Butcher]]</p>'))
      .toBe('<p>a</p><p>Play <a class="card-link" href="/card/Pudge%20Butcher">Pudge Butcher</a></p>')
    expect(cleanHtml('<pre><code>[[x]]\n</code></pre>')).toBe('<pre><code>[[x]]\n</code></pre>')
  })
})

it('unwraps paragraphs inside list items', () => {
  expect(cleanHtml('<ul><li><p>a</p></li><li><p>b</p><p>c</p></li></ul>'))
    .toBe('<ul><li>a</li><li>b<br>c</li></ul>')
})
