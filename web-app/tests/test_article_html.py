"""Visual (HTML) article editor: server-side cleaning and the submit flow."""

import sqlite3

import pytest

import webapp_config
from repositories.articles import ArticleRepository
from services.article_content import (
    html_to_text, render_markdown, sanitize_html, validate_article,
)

HTML_BODY = (
    "<h1>Why Frog decks work</h1>"
    "<p>Open with <b>tempo</b> and keep <i>pressure</i> up. Play [[Pudge Butcher]] early, "
    "and read <a href=\"https://curiosa.io/decks/abc123\">the list</a>.</p>"
    "<ul><li>Mulligan for water</li><li>Keep two sites</li></ul>"
    "<p>That's it, thanks for reading the guide! Plenty more words here to pass the "
    "minimum length check that every article has to meet before review.</p>"
)


@pytest.fixture()
def articles(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_config, "ARTICLES_DB_PATH", tmp_path / "articles.db")
    monkeypatch.setattr(webapp_config, "ARTICLE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(webapp_config, "ARTICLE_REVIEWER_IDS", ["111111111111111111"])
    return ArticleRepository()


def _login(client, uid="333333333333333333", name="Writer"):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = name
        sess["auth_provider"] = "discord"


def _submit(client, body=HTML_BODY, **extra):
    data = {"title": "Frog Tempo Primer", "summary": "How to pilot frogs.",
            "category": "Deck Guide", "tags": "frogs", "body": body, "body_format": "html"}
    data.update(extra)
    return client.post("/api/articles", data=data, content_type="multipart/form-data")


class TestSanitizer:
    @pytest.mark.parametrize("dirty", [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<img src=\"javascript:alert(1)\">",
        "<a href=\"javascript:alert(1)\">x</a>",
        "<a href=\" JaVa&#x09;script:alert(1)\">x</a>",
        "<a href=\"data:text/html,<script>alert(1)</script>\">x</a>",
        "<iframe src=\"https://evil.example\"></iframe>",
        "<svg><script>alert(1)</script></svg>",
        "<math><mi xlink:href=\"javascript:alert(1)\">x</mi></math>",
        "<noscript><p title=\"</noscript><img src=x onerror=alert(1)>\"></noscript>",
        "<p style=\"background:url(javascript:alert(1))\" onclick=\"alert(1)\">x</p>",
        "<form action=\"https://evil.example\"><input name=a></form>",
        "<object data=\"x.swf\"></object><embed src=\"x.swf\">",
        "<a href=\"//evil.example\">x</a>",
        "<style>body{display:none}</style>",
        "<p>a<!-- <script>alert(1)</script> -->b</p>",
    ])
    def test_nothing_active_survives(self, dirty):
        out = sanitize_html(dirty).lower()
        for bad in ("<script", "onerror", "onclick", "javascript:", "<iframe", "<svg",
                    "<math", "<form", "<input", "<object", "<embed", "style=", "<style",
                    "data:", "//evil", "<!--"):
            assert bad not in out, (dirty, out)

    def test_keeps_formatting(self):
        out = sanitize_html(HTML_BODY)
        assert "<h2>Why Frog decks work</h2>" in out
        assert "<strong>tempo</strong>" in out and "<em>pressure</em>" in out
        assert '<a class="card-link" href="/card/Pudge%20Butcher">Pudge Butcher</a>' in out
        assert ('<a href="https://curiosa.io/decks/abc123" target="_blank" '
                'rel="nofollow ugc noopener noreferrer">the list</a>') in out
        assert "<li>Mulligan for water</li>" in out

    def test_google_docs_style_paste(self):
        docs = ('<meta charset="utf-8"><b style="font-weight:normal;" id="docs-internal-guid-1">'
                '<p dir="ltr" style="line-height:1.38"><span style="font-size:11pt;color:#000">'
                'Hello</span></p><div><span>World</span></div></b>')
        out = sanitize_html(docs)
        assert "style" not in out and "span" not in out and "dir=" not in out
        assert "Hello" in out and "World" in out

    def test_images_need_https(self):
        assert sanitize_html('<img src="http://x.com/a.png">') == ""
        out = sanitize_html('<img src="https://x.com/a.png" alt="A deck">')
        assert out.startswith('<img src="https://x.com/a.png" alt="A deck"')
        assert 'referrerpolicy="no-referrer"' in out

    def test_tables_and_code(self):
        out = sanitize_html("<table><tr><td colspan=2 onclick=x>a<td>b</table>"
                            "<pre><code>a < b [[Not A Link]]</code></pre>")
        assert '<td colspan="2">a</td>' in out and "<td>b</td>" in out
        assert "a &lt; b [[Not A Link]]" in out

    def test_unclosed_tags_are_closed(self):
        out = sanitize_html("<p><strong>bold<em>both")
        assert out == "<p><strong>bold<em>both</em></strong></p>"

    def test_old_markdown_articles_survive_a_round_trip(self):
        md = ("## Head\n\nSome **bold** and [[Card]] and https://example.com.\n\n"
              "- a\n- b\n\n> quote\n\n```\ncode <x>\n```\n\n---\n\n1. one")
        rendered = render_markdown(md)
        cleaned = sanitize_html(rendered)
        squash = lambda s: s.replace("\n", "")  # noqa: E731
        assert squash(cleaned) == squash(rendered)
        # And cleaning is stable
        assert sanitize_html(cleaned) == cleaned

    def test_length_rules_count_text_not_tags(self):
        short = "<p>" + "<strong>x</strong>" * 50 + "</p>"
        assert "200+" in validate_article("T", "S", sanitize_html(short), "Strategy",
                                          has_pdf=False, body_format="html")
        assert html_to_text("<p>a &amp; b</p><p>c</p>") == "a & b c"


class TestHtmlSubmit:
    def test_submit_saves_cleaned_html(self, client, articles):
        _login(client)
        r = _submit(client, body=HTML_BODY + "<script>alert(1)</script>")
        assert r.status_code == 201, r.get_json()
        a = articles.get(r.get_json()["id"])
        assert a["body_format"] == "html"
        assert "<script" not in a["body_html"] and "<h2>Why Frog decks work</h2>" in a["body_html"]
        assert a["body_md"] == a["body_html"]
        assert a["word_count"] > 30

    def test_author_gets_format_back_for_editing(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        detail = client.get(f"/api/articles/{aid}").get_json()
        assert detail["body_format"] == "html" and "<h2>" in detail["body_md"]

    def test_markdown_submit_still_works(self, client, articles):
        _login(client)
        body = "## Title\n\n" + "Plain words for the article body. " * 10
        r = _submit(client, body=body, body_format="")
        a = articles.get(r.get_json()["id"])
        assert a["body_format"] == "md" and a["body_md"] == body.strip()
        assert "<h3>Title</h3>" in a["body_html"]

    def test_edit_markdown_article_into_html(self, client, articles):
        _login(client)
        aid = _submit(client, body="## Old\n\n" + "Old words. " * 30, body_format="md").get_json()["id"]
        r = client.post(f"/api/articles/{aid}/edit",
                        data={"title": "Frog Tempo Primer", "summary": "Updated.",
                              "category": "Deck Guide", "tags": "frogs",
                              "body": HTML_BODY, "body_format": "html"},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        a = articles.get(aid)
        assert a["body_format"] == "html" and "<strong>tempo</strong>" in a["body_html"]

    def test_preview_html(self, client, articles):
        _login(client)
        r = client.post("/api/articles/preview",
                        json={"body": "<p onclick=x>Hi <b>there</b></p>", "format": "html"})
        assert r.get_json()["html"] == "<p>Hi <strong>there</strong></p>"

    def test_short_html_rejected(self, client, articles):
        _login(client)
        r = _submit(client, body="<p><strong>" + "&nbsp;" * 300 + "hi</strong></p>")
        assert r.status_code == 400


def test_live_table_layout_gets_body_format(tmp_path):
    """The articles table as it is live today (before this change)."""
    db = tmp_path / "live.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL, title TEXT NOT NULL,
        summary TEXT NOT NULL, category TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '',
        body_md TEXT NOT NULL DEFAULT '', body_html TEXT NOT NULL DEFAULT '',
        word_count INTEGER NOT NULL DEFAULT 0, reading_minutes INTEGER NOT NULL DEFAULT 1,
        author_id TEXT NOT NULL, author_name TEXT NOT NULL, author_provider TEXT,
        author_avatar TEXT, pdf_file TEXT, pdf_original_name TEXT, pdf_size INTEGER,
        status TEXT NOT NULL DEFAULT 'pending', view_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT NOT NULL,
        published_at TEXT, reviewed_by TEXT, reviewed_at TEXT,
        forum_thread_id TEXT, forum_locked INTEGER NOT NULL DEFAULT 0,
        external_url TEXT, external_site TEXT, external_image TEXT,
        header_card TEXT, header_image TEXT)""")
    conn.execute("""INSERT INTO articles (slug, title, summary, category, body_md, body_html,
                    author_id, author_name, status, created_at, updated_at, submitted_at)
                    VALUES ('old', 'Old', 's', 'Strategy', '**hi**', '<p><strong>hi</strong></p>',
                    '1', 'A', 'approved', 'x', 'x', 'x')""")
    conn.commit()
    conn.close()
    repo = ArticleRepository(db_path=db)
    old = repo.get(1)
    assert old["body_format"] == "md" and old["body_html"] == "<p><strong>hi</strong></p>"
    new_id = repo.create(title="N", summary="s", category="Strategy", tags=[], body_md="<p>x</p>",
                         body_html="<p>x</p>", body_format="html", word_count=1,
                         reading_minutes=1, author_id="2", author_name="B")
    assert repo.get(new_id)["body_format"] == "html"
