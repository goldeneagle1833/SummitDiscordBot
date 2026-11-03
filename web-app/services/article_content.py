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
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

TITLE_MAX = 120
SUMMARY_MAX = 300
BODY_MAX = 40_000
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
                     has_pdf: bool, has_link: bool = False) -> str | None:
    """Return an error message, or None when the article may be saved."""
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
    if len(body) > BODY_MAX:
        return f"The article is too long ({len(body):,} characters, max {BODY_MAX:,})."
    if not has_pdf and not has_link and len(body) < 200:
        return "Write at least a few paragraphs (200+ characters), or attach a PDF."
    if len(_URL_ANYWHERE.findall(body)) > LINKS_MAX:
        return f"Too many links (max {LINKS_MAX})."
    return None


def word_count(body: str) -> int:
    return len(re.findall(r"\w+", body or ""))


def reading_minutes(body: str) -> int:
    return max(1, round(word_count(body) / 220))


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
