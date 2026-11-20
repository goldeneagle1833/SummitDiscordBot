"""Safety checks and rendering for player-submitted articles.

Two jobs:

1. ``render_markdown`` turns an article's plain text (a small Markdown subset)
   into HTML that is safe to put on the page.  Every character the author
   typed is HTML-escaped first; the only tags in the output are the handful
   this module writes itself.  Raw HTML in an article is shown as text, never
   run.  Links must be http(s) and open in a new tab with ``rel="nofollow
   ugc noopener noreferrer"``.  ``[[Card Name]]`` links to the card page.

2. ``check_pdf`` decides whether an uploaded PDF may be stored.  It must
   really be a PDF (magic bytes, end-of-file marker), not encrypted, and must
   not contain active content: JavaScript, launch/submit actions, embedded
   files, Flash/RichMedia or XFA forms.  Compressed streams are inflated (with
   a size cap) and scanned too, and ``#xx`` escapes in PDF names are decoded
   so ``/J#61vaScript`` is caught.
"""

from __future__ import annotations

import html
import re
import zlib
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

TITLE_MAX = 120
SUMMARY_MAX = 300
BODY_MAX = 40_000          # characters of text the reader sees
HTML_MAX = 150_000         # characters of cleaned HTML (tags included)
TAGS_MAX = 5
TAG_MAX_LEN = 24
LINKS_MAX = 40
PDF_MAX_BYTES = 10 * 1024 * 1024
COMMENT_MAX = 2000
EXTERNAL_URL_MAX = 500
SITE_NAME_MAX = 60

# Our own site: an article can't "link out" to another Summit page.
OWN_HOSTS = ("sorcererssummit.com",)

CATEGORIES = [
    "Strategy",
    "Deck Guide",
    "Tournament Report",
    "Limited & Draft",
    "Lore & Art",
    "Community",
    "Other",
]

# ---------------------------------------------------------------------------
# Text cleanup and validation
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")


def clean_text(value: str | None, *, multiline: bool = False) -> str:
    """Strip control and bidi-override characters; normalise newlines."""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    if not multiline:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_tags(raw) -> list[str]:
    """Tags: lowercase letters, digits, spaces and hyphens; unique; max 5."""
    if isinstance(raw, str):
        raw = raw.split(",")
    tags: list[str] = []
    for item in raw or []:
        tag = re.sub(r"[^a-z0-9 \-]", "", str(item).lower())
        tag = re.sub(r"\s+", " ", tag).strip(" -")[:TAG_MAX_LEN].strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:TAGS_MAX]


def clean_external_url(raw: str | None) -> tuple[str | None, str | None]:
    """Check a link to an article on another site.  Returns (url, error)."""
    url = clean_text(raw)
    if not url:
        return None, None
    if len(url) > EXTERNAL_URL_MAX:
        return None, f"That link is too long (max {EXTERNAL_URL_MAX} characters)."
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme.lower() not in ("http", "https") or not host or "." not in host
            or parsed.username or parsed.password or re.search(r"\s", url)):
        return None, "That doesn't look like a web link. Paste the full address (https://...)."
    if any(host == h or host.endswith("." + h) for h in OWN_HOSTS):
        return None, "That link is to this site. Link an article hosted somewhere else."
    return url, None


def site_label(url: str, site_name: str | None = None) -> str:
    """A short name for the site an outside article lives on."""
    name = clean_text(site_name)[:SITE_NAME_MAX]
    if name:
        return name
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def validate_article(title: str, summary: str, body: str, category: str,
                     has_pdf: bool, has_link: bool = False,
                     body_format: str = "md") -> str | None:
    """Return an error message, or None when the article may be saved.

    For ``body_format="html"`` the body must already be cleaned with
    :func:`sanitize_html`; the length rules count the text a reader sees.
    """
    if not title:
        return "Add a title."
    if len(title) > TITLE_MAX:
        return f"Keep the title to {TITLE_MAX} characters."
    if not summary:
        return "Add a short summary (one or two sentences)."
    if len(summary) > SUMMARY_MAX:
        return f"Keep the summary to {SUMMARY_MAX} characters."
    if category not in CATEGORIES:
        return "Pick a category."
    if body_format == "html":
        if len(body) > HTML_MAX:
            return ("The article has too much formatting to save. Try removing "
                    "some tables or pasted styling.")
        text = html_to_text(body)
        links = len(_HREF.findall(body))
    else:
        text = body
        links = len(_URL_ANYWHERE.findall(body))
    if len(text) > BODY_MAX:
        return f"The article is too long ({len(text):,} characters, max {BODY_MAX:,})."
    if not has_pdf and not has_link and len(text) < 200:
        return "Write at least a few paragraphs (200+ characters), or attach a PDF."
    if links > LINKS_MAX:
        return f"Too many links (max {LINKS_MAX})."
    return None


def word_count(body: str, body_format: str = "md") -> int:
    if body_format == "html":
        body = html_to_text(body)
    return len(re.findall(r"\w+", body or ""))


def reading_minutes(body: str, body_format: str = "md") -> int:
    return max(1, round(word_count(body, body_format) / 220))


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return slug[:60].strip("-") or "article"


# ---------------------------------------------------------------------------
# Markdown subset -> safe HTML
# ---------------------------------------------------------------------------

_URL_ANYWHERE = re.compile(r"https?://", re.IGNORECASE)

# Order matters: code first so nothing inside backticks is formatted.
_INLINE_TOKENS = re.compile(
    r"`(?P<code>[^`\n]{1,500})`"
    r"|\[\[(?P<card>[^\[\]\n|]{1,60})\]\]"
    r"|\[(?P<text>[^\[\]\n]{1,200})\]\((?P<href>https?://[^\s()<>\"']{1,500})\)"
    r"|(?P<bare>https?://[^\s<>()\[\]\"']{3,500})",
    re.IGNORECASE,
)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])")
_TOKEN_REF = re.compile("\x00(\\d+)\x00")
_LINK_ATTRS = 'target="_blank" rel="nofollow ugc noopener noreferrer"'


def _render_inline(text: str) -> str:
    """Escape ``text`` and apply inline formatting.  Output is safe HTML."""
    tokens: list[str] = []

    def stash(fragment: str) -> str:
        tokens.append(fragment)
        return f"\x00{len(tokens) - 1}\x00"

    def replace(m: re.Match) -> str:
        if m.group("code") is not None:
            return stash(f"<code>{html.escape(m.group('code'))}</code>")
        if m.group("card") is not None:
            name = m.group("card").strip()
            href = "/card/" + quote(name, safe="")
            return stash(
                f'<a class="card-link" href="{html.escape(href)}">{html.escape(name)}</a>'
            )
        if m.group("href") is not None:
            href = m.group("href")
            label = _render_inline_plain(m.group("text"))
            return stash(f'<a href="{html.escape(href)}" {_LINK_ATTRS}>{label}</a>')
        url = m.group("bare")
        trailing = ""
        while url and url[-1] in ".,;:!?":
            trailing = url[-1] + trailing
            url = url[:-1]
        return stash(
            f'<a href="{html.escape(url)}" {_LINK_ATTRS}>{html.escape(url)}</a>'
        ) + trailing

    text = text.replace("\x00", "")
    with_tokens = _INLINE_TOKENS.sub(replace, text)
    out = _render_inline_plain(with_tokens)
    return _TOKEN_REF.sub(lambda m: tokens[int(m.group(1))], out)


def _render_inline_plain(text: str) -> str:
    """Escape, then bold/italic.  Token markers (\\x00N\\x00) pass through."""
    out = html.escape(text, quote=True)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*$")
_ULIST = re.compile(r"^\s*[-*+]\s+(.*)$")
_OLIST = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_FENCE = re.compile(r"^\s*```")


def render_markdown(body: str) -> str:
    """Render the supported Markdown subset to safe HTML."""
    lines = clean_text(body, multiline=True).split("\n")
    out: list[str] = []
    para: list[str] = []
    i = 0

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_render_inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]

        if _FENCE.match(line):
            flush_para()
            i += 1
            code: list[str] = []
            while i < len(lines) and not _FENCE.match(lines[i]):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence (or end of text)
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue

        if not line.strip():
            flush_para()
            i += 1
            continue

        if _RULE.match(line):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        m = _HEADING.match(line)
        if m:
            flush_para()
            level = len(m.group(1)) + 1  # # -> h2; the page title is the h1
            out.append(f"<h{level}>{_render_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if _QUOTE.match(line):
            flush_para()
            quoted: list[str] = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quoted.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            inner = "<br>".join(_render_inline(q) for q in quoted if q.strip())
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
            continue

        for pattern, tag in ((_ULIST, "ul"), (_OLIST, "ol")):
            if pattern.match(line):
                flush_para()
                items: list[str] = []
                while i < len(lines) and pattern.match(lines[i]):
                    items.append(_render_inline(pattern.match(lines[i]).group(1)))
                    i += 1
                out.append(f"<{tag}>" + "".join(f"<li>{it}</li>" for it in items) + f"</{tag}>")
                break
        else:
            para.append(line.strip())
            i += 1

    flush_para()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML from the visual editor -> safe HTML
# ---------------------------------------------------------------------------
#
# The editor sends HTML.  Nothing it sends is trusted: the HTML is parsed and
# a fresh copy is written out that holds only the tags and attributes listed
# below.  Text is always re-escaped, so whatever the parser makes of odd input
# can only ever come out as text.  Scripts, styles, frames, forms, event
# handlers, inline styles and classes are all dropped.

# Tags kept as they are.
_KEEP_TAGS = {
    "p", "br", "h2", "h3", "h4", "strong", "em", "u", "s", "sub", "sup",
    "blockquote", "ul", "ol", "li", "a", "code", "pre", "hr", "img",
    "table", "thead", "tbody", "tr", "th", "td", "figure", "figcaption",
}
# Tags written out as a kept tag instead.
_RENAME_TAGS = {
    "b": "strong", "i": "em", "strike": "s", "del": "s", "ins": "u",
    "h1": "h2", "h5": "h4", "h6": "h4", "tfoot": "tbody", "kbd": "code",
    "tt": "code", "samp": "code",
    # Word processors and contentEditable wrap lines in these.
    "div": "p", "section": "p", "article": "p", "header": "p", "footer": "p",
    "main": "p", "aside": "p", "address": "p", "center": "p", "dd": "p",
    "dt": "p", "caption": "p",
}
# Tags removed together with everything inside them.
_DROP_WITH_CONTENT = {
    "script", "style", "iframe", "frameset", "object",
    "applet", "noscript", "noembed", "noframes", "template", "svg", "math",
    "head", "title", "textarea", "select", "button", "form",
    "audio", "video", "canvas", "map", "xml",
}
# Empty (void) tags that are simply ignored.  They have no end tag, so they
# must never start a "drop everything inside" run.
_IGNORED_VOID_TAGS = {
    "meta", "link", "base", "embed", "frame", "input", "param", "source",
    "track", "area", "wbr", "col", "keygen", "image", "basefont", "isindex",
}
_VOID_TAGS = {"br", "hr", "img"}
# A new one of these closes an open paragraph, as browsers do.
_BLOCK_TAGS = {
    "p", "h2", "h3", "h4", "blockquote", "ul", "ol", "li", "pre", "hr",
    "table", "thead", "tbody", "tr", "th", "td", "figure", "figcaption",
}
_HEADINGS = {"h2", "h3", "h4"}
_CONTAINERS = {"li", "ul", "ol", "blockquote", "td", "th", "tr", "table",
               "thead", "tbody", "figure", "figcaption", "pre"}
_MAX_DEPTH = 40
_CARD_REF = re.compile(r"\[\[([^\[\]\n|]{1,60})\]\]")
_HREF = re.compile(r'<a href="')
_TAG = re.compile(r"<[^>]*>")
_EMPTY_BLOCK = re.compile(r"<(p|h2|h3|h4|li|blockquote|figcaption)>(?:\s|&nbsp;|<br>)*</\1>")


def _safe_href(raw: str | None) -> tuple[str | None, bool]:
    """(href, is_card_link) for a link the author added, or (None, False)."""
    href = re.sub(r"[\x00-\x20\x7f]", "", raw or "")
    if not href or len(href) > 500:
        return None, False
    if href.startswith("/card/") and "//" not in href and "\\" not in href:
        return href, True
    m = re.match(r"^(https?):", href, re.IGNORECASE)
    if m and urlparse(href).hostname:
        return href, False
    if re.match(r"^mailto:[^\s@]+@[^\s@]+$", href, re.IGNORECASE):
        return href, False
    return None, False


def _safe_src(raw: str | None) -> str | None:
    src = re.sub(r"[\x00-\x20\x7f]", "", raw or "")
    if not src or len(src) > 1000:
        return None
    if re.match(r"^https://", src, re.IGNORECASE) and urlparse(src).hostname:
        return src
    if src.startswith("/card-images/") and "//" not in src and ".." not in src:
        return src
    return None


def _small_int(raw: str | None, low: int, high: int) -> int | None:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return n if low <= n <= high else None


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple[str, bool]] = []  # (tag, written to output?)
        self.skip_depth = 0
        self.skip_tag: str | None = None

    # -- helpers -----------------------------------------------------------
    def _written(self) -> list[str]:
        return [t for t, written in self.stack if written]

    def _inside(self, *tags: str) -> bool:
        return any(t in tags for t in self._written())

    def _close_until(self, tag: str) -> None:
        """Close open tags down to and including the last ``tag``."""
        if not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            t, written = self.stack.pop()
            if written:
                self.out.append(f"</{t}>")
            if t == tag:
                break

    def _close_implied(self, name: str) -> None:
        """End elements a browser would end before ``name`` starts."""
        if name in _BLOCK_TAGS:
            # An open paragraph or heading ends at the next block, but only up
            # to the nearest container (list item, quote, table cell...).
            for t in reversed(self._written()):
                if t == "p" or t in _HEADINGS:
                    self._close_until(t)
                    break
                if t in _CONTAINERS:
                    break
        # A new list item / row / cell ends the previous sibling.
        siblings = {"li": ({"li"}, {"ul", "ol"}),
                    "tr": ({"tr"}, {"table", "thead", "tbody"}),
                    "td": ({"td", "th"}, {"tr", "table"}),
                    "th": ({"td", "th"}, {"tr", "table"})}
        if name in siblings:
            same, parents = siblings[name]
            for t in reversed(self._written()):
                if t in same:
                    self._close_until(t)
                    break
                if t in parents:
                    break

    # -- parser callbacks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        if tag in _IGNORED_VOID_TAGS:
            return
        if tag in _DROP_WITH_CONTENT:
            self.skip_tag, self.skip_depth = tag, 1
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        name = _RENAME_TAGS.get(tag, tag)
        # Google Docs wraps a whole paste in <b style="font-weight:normal">.
        if name == "strong" and re.search(r"font-weight:\s*(normal|400)", a.get("style", ""), re.I):
            name = "span"
        if name not in _KEEP_TAGS:
            if tag not in _VOID_TAGS:
                self.stack.append((tag, False))
            return

        self._close_implied(name)
        if len(self.stack) >= _MAX_DEPTH:
            return

        parts = [name]
        if name == "a":
            href, is_card = _safe_href(a.get("href"))
            if not href or self._inside("a"):
                self.stack.append((tag, False))
                return
            if is_card:
                parts.append(f'class="card-link" href="{html.escape(href)}"')
            else:
                parts.append(f'href="{html.escape(href)}" {_LINK_ATTRS}')
        elif name == "img":
            src = _safe_src(a.get("src"))
            if not src:
                return
            alt = clean_text(a.get("alt"))[:200]
            parts.append(f'src="{html.escape(src)}" alt="{html.escape(alt)}" '
                         'loading="lazy" referrerpolicy="no-referrer"')
        elif name in ("td", "th"):
            for key in ("colspan", "rowspan"):
                n = _small_int(a.get(key), 2, 20)
                if n:
                    parts.append(f'{key}="{n}"')
        elif name == "ol":
            n = _small_int(a.get("start"), 0, 9999)
            if n is not None and n != 1:
                parts.append(f'start="{n}"')

        self.out.append("<" + " ".join(parts) + ">")
        if name not in _VOID_TAGS:
            self.stack.append((name, True))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        tag = tag.lower()
        if not self.skip_depth and tag not in _VOID_TAGS and \
                _RENAME_TAGS.get(tag, tag) not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if not self.skip_depth:
                    self.skip_tag = None
            return
        name = _RENAME_TAGS.get(tag, tag)
        if name in _VOID_TAGS and name in _KEEP_TAGS:
            if name == "br":   # a stray </br> is a line break in browsers
                self.out.append("<br>")
            return
        # Find the matching open tag (by original or written name).
        for i in range(len(self.stack) - 1, -1, -1):
            t, written = self.stack[i]
            if t == tag or (written and t == name):
                while len(self.stack) > i:
                    t2, w2 = self.stack.pop()
                    if w2:
                        self.out.append(f"</{t2}>")
                return

    def handle_data(self, data):
        if self.skip_depth or not data:
            return
        data = _CONTROL_CHARS.sub("", data)
        if self._inside("pre", "code", "a"):
            self.out.append(html.escape(data, quote=False))
            return
        pos = 0
        for m in _CARD_REF.finditer(data):
            self.out.append(html.escape(data[pos:m.start()], quote=False))
            name = m.group(1).strip()
            href = "/card/" + quote(name, safe="")
            self.out.append(f'<a class="card-link" href="{html.escape(href)}">'
                            f"{html.escape(name)}</a>")
            pos = m.end()
        self.out.append(html.escape(data[pos:], quote=False))

    def close(self):
        super().close()
        while self.stack:
            t, written = self.stack.pop()
            if written:
                self.out.append(f"</{t}>")


def sanitize_html(raw: str | None) -> str:
    """Clean HTML from the article editor down to the allowed tags."""
    raw = (raw or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if len(raw) > HTML_MAX * 4:
        raw = raw[: HTML_MAX * 4]
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    out = "".join(parser.out)
    # Blank paragraphs from pressing Enter twice, empty headings, etc.
    prev = None
    while prev != out:
        prev = out
        out = _EMPTY_BLOCK.sub("", out)
    # Put each block on its own line so the HTML view is readable.
    out = re.sub(r"\s*(</(?:p|h2|h3|h4|blockquote|ul|ol|li|pre|table|tr|figure)>|<hr>)\s*",
                 r"\1\n", out)
    out = re.sub(r"(<(?:ul|ol|table|thead|tbody|tr|blockquote|figure)(?: [^>]*)?>)\s*", r"\1\n", out)
    out = re.sub(r"\n{2,}", "\n", out)
    return out.strip()


def html_to_text(clean_html: str) -> str:
    """The words a reader sees in cleaned article HTML."""
    text = _TAG.sub(" ", clean_html or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# PDF checks
# ---------------------------------------------------------------------------

# Names that mean the PDF can run code, phone home, or carry other files.
_BLOCKED_PDF_NAMES = {
    b"javascript", b"js", b"launch", b"embeddedfile", b"embeddedfiles",
    b"richmedia", b"xfa", b"submitform", b"importdata", b"gotoe",
}
_PDF_NAME = re.compile(rb"/([^\s/<>\[\]()%{}]{1,64})")
_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
_INFLATE_CAP = 40 * 1024 * 1024


def _decode_name(raw: bytes) -> bytes:
    return re.sub(rb"#([0-9A-Fa-f]{2})", lambda m: bytes([int(m.group(1), 16)]), raw)


def _blocked_name_in(data: bytes) -> bytes | None:
    for m in _PDF_NAME.finditer(data):
        name = _decode_name(m.group(1)).lower()
        if name in _BLOCKED_PDF_NAMES:
            return name
    return None


def check_pdf(data: bytes) -> str | None:
    """Return an error message, or None when the PDF is safe to store."""
    if not data:
        return "The PDF is empty."
    if len(data) > PDF_MAX_BYTES:
        return f"PDFs can be up to {PDF_MAX_BYTES // (1024 * 1024)} MB."
    if not data.startswith(b"%PDF-"):
        return "That file isn't a PDF."
    if b"%%EOF" not in data[-2048:]:
        return "That PDF looks incomplete. Export it again and retry."
    if re.search(rb"/Encrypt(?![A-Za-z0-9])", data):
        return "Password-protected PDFs can't be checked. Export it without a password."

    blocked = _blocked_name_in(data)
    if blocked is None:
        inflated_total = 0
        for m in _STREAM.finditer(data):
            chunk = m.group(1)
            try:
                d = zlib.decompressobj()
                inflated = d.decompress(chunk, _INFLATE_CAP - inflated_total)
            except zlib.error:
                continue
            inflated_total += len(inflated)
            blocked = _blocked_name_in(inflated)
            if blocked is not None or inflated_total >= _INFLATE_CAP:
                break
        if inflated_total >= _INFLATE_CAP and blocked is None:
            return "That PDF is too complex to check. Try a simpler export."
    if blocked is not None:
        return (
            "That PDF has scripts, attachments or other active content, which "
            "we don't allow. Export or \"Print to PDF\" a plain copy and retry."
        )
    return None
