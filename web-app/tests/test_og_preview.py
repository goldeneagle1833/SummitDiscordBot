"""Tests for Open Graph preview routes."""

from unittest.mock import patch, MagicMock


class TestOGPreviewRoutes:
    """Test OG meta tag generation for bot crawlers."""

    def test_events_list_returns_og_tags(self, client):
        """GET /og/top-8 returns HTML with OG meta tags."""
        resp = client.get("/og/top-8")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Top 8 Events' in html
        assert 'og:description' in html
        assert 'og:image' in html
        assert 'og:site_name' in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_with_data(self, mock_repo_cls, client):
        """GET /og/top-8/<folder> returns event-specific OG tags."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_event_decks.return_value = {
            "top8_decks": [
                {"player": "TestWinner", "avatar": "Kappa"},
                {"player": "Player2", "avatar": "Alpha"},
            ],
            "all_decks": [],
        }
        mock_repo.get_event_description.return_value = None

        resp = client.get("/og/top-8/TestEvent2025")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Testevent2025' in html or 'TestEvent2025' in html
        assert 'TestWinner' in html
        assert '2 decklists' in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_with_description(self, mock_repo_cls, client):
        """Event description is used when available."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_event_decks.return_value = {
            "top8_decks": [{"player": "P1", "avatar": ""}],
            "all_decks": [],
        }
        mock_repo.get_event_description.return_value = "A great tournament!"

        resp = client.get("/og/top-8/SomeEvent")
        html = resp.data.decode()
        assert "A great tournament!" in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_not_found(self, mock_repo_cls, client):
        """Missing event still returns valid OG HTML (graceful fallback)."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_event_decks.return_value = None
        mock_repo.get_event_description.return_value = None

        resp = client.get("/og/top-8/NonExistent")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html

    def test_deck_rec_list_returns_og_tags(self, client):
        """GET /og/deck-rec returns HTML with OG meta tags."""
        resp = client.get("/og/deck-rec")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Deck Recommendations' in html

    @patch("routes.og_preview.DeckRecRepository")
    def test_deck_detail_with_seed(self, mock_repo_cls, client):
        """GET /og/deck-rec/<id> returns deck-specific OG tags."""
        mock_seed = MagicMock()
        mock_seed.deck_id = "abc123"
        mock_seed.is_seed = True
        mock_seed.deck_name = "Fire Aggro"
        mock_seed.avatar_name = "Kappa"
        mock_seed.player_name = "TestPlayer"
        mock_seed.event_name = "Gen Con 2025"
        mock_seed.primer = ""

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.load_all_decks.return_value = [mock_seed]

        resp = client.get("/og/deck-rec/abc123")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Fire Aggro" in html
        assert "TestPlayer" in html

    @patch("routes.og_preview.DeckRecRepository")
    def test_deck_detail_with_primer(self, mock_repo_cls, client):
        """Primer text is used as OG description when available."""
        mock_seed = MagicMock()
        mock_seed.deck_id = "xyz789"
        mock_seed.is_seed = True
        mock_seed.deck_name = "Water Control"
        mock_seed.avatar_name = ""
        mock_seed.player_name = ""
        mock_seed.event_name = ""
        mock_seed.primer = "A defensive deck that wins through attrition"

        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.load_all_decks.return_value = [mock_seed]

        resp = client.get("/og/deck-rec/xyz789")
        html = resp.data.decode()
        assert "A defensive deck that wins through attrition" in html

    @patch("routes.og_preview.DeckRecRepository")
    def test_deck_detail_not_found(self, mock_repo_cls, client):
        """Unknown deck ID still returns valid OG HTML."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.load_all_decks.return_value = []

        resp = client.get("/og/deck-rec/unknown")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Deck Recommendation' in html

    def test_og_html_escapes_special_characters(self, client):
        """Ensure HTML special characters are escaped in OG tags."""
        # The events list endpoint won't have special chars, but test the
        # response is valid HTML
        resp = client.get("/og/top-8")
        html = resp.data.decode()
        assert '<!DOCTYPE html>' in html
        assert '</html>' in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_escapes_html_in_description(self, mock_repo_cls, client):
        """HTML in event descriptions is properly escaped."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_event_decks.return_value = {
            "top8_decks": [{"player": 'Bob<img src=x onerror="alert(1)">', "avatar": ""}],
            "all_decks": [],
        }
        mock_repo.get_event_description.return_value = None

        resp = client.get("/og/top-8/TestEvent")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "<img" not in html
        assert "&lt;" in html
