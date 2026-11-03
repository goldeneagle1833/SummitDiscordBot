"""Player articles: safe rendering, PDF checks, submit/review flow, DMs."""

import io
import zlib

import pytest

import webapp_config
from repositories.articles import ArticleRepository
from services.article_content import check_pdf, render_markdown

BODY = (
    "## Why Frog decks work\n\n"
    "Open with **tempo** and keep *pressure* up. Play [[Pudge Butcher]] early.\n\n"
    "- Mulligan for water\n- Keep two sites\n\n"
    "More at https://curiosa.io/decks/abc123. That's it, thanks for reading the guide!"
)


def _pdf(extra: bytes = b"") -> bytes:
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Summit guide")
    c.save()
    data = buf.getvalue()
    if extra:
        # Splice an object in before the trailer; enough for the scanner.
        idx = data.rfind(b"xref")
        data = data[:idx] + extra + b"\n" + data[idx:]
    return data


@pytest.fixture()
def articles(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp_config, "ARTICLES_DB_PATH", tmp_path / "articles.db")
    monkeypatch.setattr(webapp_config, "ARTICLE_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(webapp_config, "ARTICLE_REVIEWER_IDS", ["111111111111111111", "222222222222222222"])
    return ArticleRepository()


def _login(client, uid="333333333333333333", name="Writer", provider="discord"):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = name
        sess["auth_provider"] = provider


def _submit(client, **overrides):
    data = {"title": "Frog Tempo Primer", "summary": "How to pilot frogs.",
            "category": "Deck Guide", "tags": "frogs, Tempo, water!!", "body": BODY}
    data.update(overrides)
    return client.post("/api/articles", data=data, content_type="multipart/form-data")


# ---------------------------------------------------------------------------
# Rendering


class TestRenderMarkdown:
    def test_html_is_escaped_not_run(self):
        out = render_markdown('<script>alert(1)</script> <img src=x onerror=alert(1)>')
        assert "<script" not in out and "<img" not in out
        assert "&lt;script&gt;" in out

    def test_javascript_links_are_not_links(self):
        out = render_markdown("[click](javascript:alert(1))")
        assert "href" not in out

    def test_attribute_breakout_in_url(self):
        out = render_markdown('https://example.com/"onmouseover="alert(1)')
        assert 'onmouseover="' not in out

    def test_supported_formatting(self):
        out = render_markdown(BODY)
        assert "<h3>Why Frog decks work</h3>" in out
        assert "<strong>tempo</strong>" in out and "<em>pressure</em>" in out
        assert '<a class="card-link" href="/card/Pudge%20Butcher">Pudge Butcher</a>' in out
        assert "<ul><li>Mulligan for water</li><li>Keep two sites</li></ul>" in out
        assert 'href="https://curiosa.io/decks/abc123"' in out
        assert 'rel="nofollow ugc noopener noreferrer"' in out
        # trailing full stop is not part of the link
        assert "abc123</a>." in out

    def test_code_is_literal(self):
        out = render_markdown("```\n<b>**x**</b>\n```")
        assert "<pre><code>&lt;b&gt;**x**&lt;/b&gt;</code></pre>" == out


# ---------------------------------------------------------------------------
# PDF checks


class TestCheckPdf:
    def test_plain_pdf_passes(self):
        assert check_pdf(_pdf()) is None

    def test_not_a_pdf(self):
        assert "isn't a PDF" in check_pdf(b"<html><script>x</script></html>%%EOF")

    def test_javascript_rejected(self):
        assert check_pdf(_pdf(b"9 0 obj << /S /JavaScript /JS (app.alert(1)) >> endobj"))

    def test_hex_escaped_name_rejected(self):
        assert check_pdf(_pdf(b"9 0 obj << /S /J#61vaScript >> endobj"))

    def test_javascript_hidden_in_compressed_stream_rejected(self):
        hidden = zlib.compress(b"<< /OpenAction << /S /Launch /F (cmd.exe) >> >>")
        obj = b"9 0 obj << /Filter /FlateDecode >> stream\n" + hidden + b"\nendstream endobj"
        assert check_pdf(_pdf(obj))

    def test_embedded_file_rejected(self):
        assert check_pdf(_pdf(b"9 0 obj << /Type /EmbeddedFile >> endobj"))

    def test_encrypted_rejected(self):
        assert "Password" in check_pdf(_pdf(b"9 0 obj << /Encrypt 10 0 R >> endobj"))

    def test_too_big(self):
        assert "10 MB" in check_pdf(b"%PDF-" + b"0" * (10 * 1024 * 1024) + b"%%EOF")


# ---------------------------------------------------------------------------
# API flow


class TestSubmitAndReview:
    def test_login_required(self, client, articles):
        assert _submit(client).status_code == 401

    def test_submit_holds_for_review_and_pings_reviewers(self, client, articles):
        _login(client)
        resp = _submit(client)
        assert resp.status_code == 201, resp.get_json()
        aid = resp.get_json()["id"]

        a = articles.get(aid)
        assert a["status"] == "pending"
        assert a["tags"] == ["frogs", "tempo", "water"]
        assert "<script" not in a["body_html"]

        pings = articles.notifications("pending")
        assert {n["recipient"] for n in pings} == {"111111111111111111", "222222222222222222"}
        assert all(n["audience"] == "reviewer" for n in pings)
        assert pings[0]["link_path"] == f"/admin/articles?id={aid}"

        # Not public yet
        with client.session_transaction() as sess:
            sess.clear()
        assert client.get(f"/api/articles/{aid}").status_code == 404
        assert client.get("/api/articles").get_json()["total"] == 0

    def test_validation(self, client, articles):
        _login(client)
        assert _submit(client, title="").status_code == 400
        assert _submit(client, category="Nope").status_code == 400
        assert _submit(client, body="too short").status_code == 400

    def test_daily_limit(self, client, articles):
        _login(client)
        for _ in range(3):
            assert _submit(client).status_code == 201
        assert _submit(client).status_code == 429

    def test_regular_user_cannot_review(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        assert client.get("/api/articles/review").status_code == 403
        r = client.post(f"/api/articles/{aid}/review", json={"action": "approve"})
        assert r.status_code == 403

    def test_reviewer_comment_dms_discord_author(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        _login(client, uid="111111111111111111", name="Bruce")
        r = client.post(f"/api/articles/{aid}/review",
                        json={"action": "request_changes", "comment": "Add a sideboard section."})
        assert r.status_code == 200
        assert articles.get(aid)["status"] == "changes_requested"
        dm = [n for n in articles.notifications() if n["audience"] == "author"]
        assert len(dm) == 1
        assert dm[0]["recipient"] == "333333333333333333"
        assert "Add a sideboard section." in dm[0]["body"]

        # Request changes needs a comment
        r = client.post(f"/api/articles/{aid}/review", json={"action": "request_changes"})
        assert r.status_code == 400

    def test_google_author_gets_no_dm_but_sees_comments(self, client, articles):
        _login(client, uid="104857600000000000001", name="Gina", provider="google")
        aid = _submit(client).get_json()["id"]
        _login(client, uid="111111111111111111", name="Bruce")
        client.post(f"/api/articles/{aid}/comments", json={"body": "Nice one"})
        assert not [n for n in articles.notifications() if n["audience"] == "author"]
        _login(client, uid="104857600000000000001", name="Gina", provider="google")
        data = client.get(f"/api/articles/{aid}").get_json()
        assert [c["body"] for c in data["comments"] if c["kind"] == "comment"] == ["Nice one"]

    def test_approve_publishes_and_search_filters(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        _submit(client, title="Limited notes", category="Limited & Draft",
                tags="draft", body=BODY.replace("Frog", "Draft"))
        _login(client, uid="111111111111111111", name="Bruce")
        r = client.post(f"/api/articles/{aid}/review", json={"action": "approve"})
        assert r.get_json()["status"] == "approved"
        assert any("live" in n["subject"] for n in articles.notifications())

        with client.session_transaction() as sess:
            sess.clear()
        listing = client.get("/api/articles").get_json()
        assert listing["total"] == 1  # only the approved one
        assert "body_md" not in listing["articles"][0]
        assert client.get("/api/articles?q=frog tempo").get_json()["total"] == 1
        assert client.get("/api/articles?q=nothinglikethis").get_json()["total"] == 0
        assert client.get("/api/articles?tag=frogs").get_json()["total"] == 1
        assert client.get("/api/articles?category=Strategy").get_json()["total"] == 0
        assert client.get("/api/articles?author=333333333333333333").get_json()["total"] == 1

        detail = client.get(f"/api/articles/{aid}").get_json()
        assert "<h3>" in detail["body_html"]
        assert "comments" not in detail and "body_md" not in detail
        assert articles.get(aid)["view_count"] == 1
        client.get(f"/api/articles/{aid}")
        assert articles.get(aid)["view_count"] == 1  # same visitor counted once

        facets = client.get("/api/articles/facets").get_json()
        assert facets["categories"] == {"Deck Guide": 1}

    def test_author_edit_sends_back_to_review(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        _login(client, uid="111111111111111111", name="Bruce")
        client.post(f"/api/articles/{aid}/review", json={"action": "approve"})
        _login(client)
        r = client.post(f"/api/articles/{aid}/edit",
                        data={"title": "Frog Tempo Primer v2", "summary": "Updated.",
                              "category": "Deck Guide", "tags": "frogs", "body": BODY},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        a = articles.get(aid)
        assert a["status"] == "pending" and a["slug"] == "frog-tempo-primer-v2"

    def test_other_user_cannot_edit_or_delete(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        _login(client, uid="444444444444444444", name="Other")
        r = client.post(f"/api/articles/{aid}/edit", data={"title": "x"},
                        content_type="multipart/form-data")
        assert r.status_code == 404
        assert client.delete(f"/api/articles/{aid}").status_code == 404
        assert client.get(f"/api/articles/{aid}").status_code == 404

    def test_pdf_upload_stored_outside_static_and_gated(self, client, articles, tmp_path):
        _login(client)
        resp = client.post(
            "/api/articles",
            data={"title": "PDF guide", "summary": "See the PDF.", "category": "Strategy",
                  "body": "", "pdf": (io.BytesIO(_pdf()), "guide.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201, resp.get_json()
        aid = resp.get_json()["id"]
        a = articles.get(aid)
        stored = tmp_path / "uploads" / a["pdf_file"]
        assert stored.exists() and "static" not in str(stored)

        assert client.get(f"/api/articles/{aid}/pdf").status_code == 200  # author
        with client.session_transaction() as sess:
            sess.clear()
        assert client.get(f"/api/articles/{aid}/pdf").status_code == 404  # not public yet

        _login(client, uid="111111111111111111", name="Bruce")
        client.post(f"/api/articles/{aid}/review", json={"action": "approve"})
        with client.session_transaction() as sess:
            sess.clear()
        r = client.get(f"/api/articles/{aid}/pdf")
        assert r.status_code == 200
        assert r.mimetype == "application/pdf"
        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_bad_pdf_rejected(self, client, articles):
        _login(client)
        evil = _pdf(b"9 0 obj << /S /JavaScript /JS (app.alert(1)) >> endobj")
        resp = client.post(
            "/api/articles",
            data={"title": "PDF", "summary": "x", "category": "Strategy", "body": "",
                  "pdf": (io.BytesIO(evil), "guide.pdf")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "active content" in resp.get_json()["error"]
        disguised = client.post(
            "/api/articles",
            data={"title": "PDF", "summary": "x", "category": "Strategy", "body": "",
                  "pdf": (io.BytesIO(b"<html></html>"), "guide.pdf")},
            content_type="multipart/form-data",
        )
        assert disguised.status_code == 400

    def test_author_reply_pings_reviewers_once(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        before = len(articles.notifications())
        client.post(f"/api/articles/{aid}/comments", json={"body": "Thanks, will fix"})
        # Reviewers were pinged at submission moments ago, so the cooldown holds
        assert len(articles.notifications()) == before

    def test_me_flags_reviewer(self, client, articles):
        _login(client, uid="222222222222222222", name="ofncj")
        assert client.get("/api/me").get_json()["is_article_reviewer"] is True
        _login(client)
        assert client.get("/api/me").get_json()["is_article_reviewer"] is False


class TestReviewerList:
    def test_only_admins_manage_reviewers(self, client, articles):
        _login(client)
        assert client.get("/api/articles/reviewers").status_code == 403
        assert client.post("/api/articles/reviewers", json={"user_id": "555555555555555555"}).status_code == 403

    def test_added_reviewer_can_review_and_gets_pings(self, client, articles, monkeypatch):
        monkeypatch.setattr(webapp_config, "ARTICLE_REVIEWER_IDS", [])
        with client.session_transaction() as sess:
            sess["user_id"] = "admin_user_1"
            sess["username"] = "Admin"
        r = client.post("/api/articles/reviewers", json={"user_id": "555555555555555555", "username": "ofncj"})
        assert r.status_code == 201
        assert [x["username"] for x in r.get_json()["reviewers"]] == ["ofncj"]
        assert client.post("/api/articles/reviewers", json={"user_id": "abc"}).status_code == 400

        _login(client, uid="555555555555555555", name="ofncj")
        assert client.get("/api/me").get_json()["is_article_reviewer"] is True
        assert client.get("/api/articles/review").status_code == 200
        _login(client)
        _submit(client)
        assert [n["recipient"] for n in articles.notifications()] == ["555555555555555555"]

        with client.session_transaction() as sess:
            sess["user_id"] = "admin_user_1"
        assert client.delete("/api/articles/reviewers/555555555555555555").status_code == 200
        _login(client, uid="555555555555555555", name="ofncj")
        assert client.get("/api/articles/review").status_code == 403


class TestDiscussion:
    def _published(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        _login(client, uid="111111111111111111", name="Bruce")
        client.post(f"/api/articles/{aid}/review", json={"action": "approve"})
        return aid

    def test_comments_only_on_published_articles(self, client, articles):
        _login(client)
        aid = _submit(client).get_json()["id"]
        assert client.post(f"/api/articles/{aid}/discussion", json={"body": "hi"}).status_code == 404
        assert client.get(f"/api/articles/{aid}/discussion").status_code == 404

    def test_post_list_and_queue_for_discord(self, client, articles, monkeypatch):
        monkeypatch.setattr(webapp_config, "DISCORD_GUILD_ID", "123")
        aid = self._published(client, articles)
        with client.session_transaction() as sess:
            sess.clear()
        assert client.post(f"/api/articles/{aid}/discussion", json={"body": "hi"}).status_code == 401

        _login(client, uid="444444444444444444", name="Reader")
        r = client.post(f"/api/articles/{aid}/discussion", json={"body": "<b>Nice</b> guide"})
        assert r.status_code == 201
        c = r.get_json()["comments"][0]
        assert c["body"] == "<b>Nice</b> guide"  # stored as text; React escapes it
        assert c["can_delete"] is True and "user_id" not in c
        stored = articles.get_public_comment(c["id"])
        assert stored["mirror_status"] == "pending" and stored["source"] == "site"

        # A Discord-side comment shows up for everyone, not deletable by readers
        articles.add_public_comment(aid, source="discord", user_id="42", username="Disco",
                                    avatar=None, body="From Discord", discord_message_id="6001")
        con = __import__("sqlite3").connect(webapp_config.ARTICLES_DB_PATH)
        con.execute("UPDATE articles SET forum_thread_id = '777' WHERE id = ?", (aid,))
        con.commit(); con.close()
        with client.session_transaction() as sess:
            sess.clear()
        d = client.get(f"/api/articles/{aid}/discussion").get_json()
        assert [x["body"] for x in d["comments"]] == ["<b>Nice</b> guide", "From Discord"]
        assert d["discord_thread_url"] == "https://discord.com/channels/123/777"
        assert not any(x["can_delete"] for x in d["comments"])

    def test_delete_rules_and_rate_limit(self, client, articles):
        aid = self._published(client, articles)
        _login(client, uid="444444444444444444", name="Reader")
        cid = client.post(f"/api/articles/{aid}/discussion", json={"body": "first"}).get_json()["comments"][0]["id"]
        _login(client, uid="555555555555555555", name="Other")
        assert client.delete(f"/api/articles/{aid}/discussion/{cid}").status_code == 403
        _login(client, uid="444444444444444444", name="Reader")
        assert client.delete(f"/api/articles/{aid}/discussion/{cid}").status_code == 200
        assert articles.get_public_comment(cid)["deleted"] == 1
        for i in range(9):
            assert client.post(f"/api/articles/{aid}/discussion", json={"body": f"c{i}"}).status_code == 201
        assert client.post(f"/api/articles/{aid}/discussion", json={"body": "too many"}).status_code == 429
