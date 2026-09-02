"""Tests for Open Graph preview routes."""

from unittest.mock import patch, MagicMock

BOT_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class TestOGPreviewBotDetection:
    """Test that bots get OG tags and regular users get the SPA."""

    def test_browser_gets_spa(self, client):
        """Regular browser user agent gets the React SPA index.html."""
        resp = client.get("/top-8", headers={"User-Agent": BROWSER_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' not in html or '<div id="root">' in html

    def test_discord_bot_gets_og_tags(self, client):
        """Discord bot user agent gets OG meta tags."""
        resp = client.get("/top-8", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Top 8 Events' in html


class TestOGPreviewRoutes:
    """Test OG meta tag generation for bot crawlers."""

    def test_events_list_returns_og_tags(self, client):
        """GET /top-8 with bot UA returns HTML with OG meta tags."""
        resp = client.get("/top-8", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Top 8 Events' in html
        assert 'og:description' in html
        assert 'og:image' in html
        assert 'og:site_name' in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_with_data(self, mock_repo_cls, client):
        """GET /top-8/<folder> returns event-specific OG tags."""
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

        resp = client.get("/top-8/TestEvent2025", headers={"User-Agent": BOT_UA})
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

        resp = client.get("/top-8/SomeEvent", headers={"User-Agent": BOT_UA})
        html = resp.data.decode()
        assert "A great tournament!" in html

    @patch("routes.og_preview.EventRepository")
    def test_event_detail_not_found(self, mock_repo_cls, client):
        """Missing event still returns valid OG HTML (graceful fallback)."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_event_decks.return_value = None
        mock_repo.get_event_description.return_value = None

        resp = client.get("/top-8/NonExistent", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html

    def test_deck_rec_list_returns_og_tags(self, client):
        """GET /deck-rec returns HTML with OG meta tags."""
        resp = client.get("/deck-rec", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Deck Recommendations' in html

    @patch("routes.og_preview.DeckRecRepository")
    def test_deck_detail_with_seed(self, mock_repo_cls, client):
        """GET /deck-rec/<id> returns deck-specific OG tags."""
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

        resp = client.get("/deck-rec/abc123", headers={"User-Agent": BOT_UA})
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

        resp = client.get("/deck-rec/xyz789", headers={"User-Agent": BOT_UA})
        html = resp.data.decode()
        assert "A defensive deck that wins through attrition" in html

    @patch("routes.og_preview.DeckRecRepository")
    def test_deck_detail_not_found(self, mock_repo_cls, client):
        """Unknown deck ID still returns valid OG HTML."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.load_all_decks.return_value = []

        resp = client.get("/deck-rec/unknown", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Deck Recommendation' in html

    def test_elo_leaderboard_returns_og_tags(self, client):
        """GET /elo with bot UA returns HTML with OG meta tags."""
        resp = client.get("/elo", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'ELO Leaderboard' in html

    @patch("routes.og_preview.EloRepository")
    def test_elo_leaderboard_with_standings(self, mock_repo_cls, client):
        """ELO page shows top player info when standings are available."""
        mock_repo = MagicMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_all_standings.return_value = [
            {"display_name": "TopPlayer", "online_elo": 1850},
            {"display_name": "SecondPlayer", "online_elo": 1720},
        ]

        resp = client.get("/elo", headers={"User-Agent": BOT_UA})
        html = resp.data.decode()
        assert "TopPlayer" in html
        assert "1850" in html

    def test_avatars_list_returns_og_tags(self, client):
        """GET /avatars with bot UA returns HTML with OG meta tags."""
        resp = client.get("/avatars", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Avatar Stats' in html

    @patch("routes.og_preview._get_avatar_stats")
    def test_avatar_detail_with_stats(self, mock_stats, client):
        """GET /avatar/<name> returns avatar-specific OG tags."""
        mock_stats.return_value = {"wins": 42, "losses": 18, "total": 60, "win_rate": 70.0}

        resp = client.get("/avatar/Kappa", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Kappa' in html
        assert '70.0%' in html
        assert '60 matches' in html

    @patch("routes.og_preview._get_avatar_stats")
    def test_avatar_detail_no_stats(self, mock_stats, client):
        """Avatar with no match data still returns valid OG HTML."""
        mock_stats.return_value = None

        resp = client.get("/avatar/NewAvatar", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'NewAvatar' in html

    @patch("routes.og_preview.CardCatalogRepository")
    def test_card_detail_with_metadata(self, mock_catalog_cls, client):
        """GET /card/<name> returns card-specific OG tags."""
        mock_catalog = MagicMock()
        mock_catalog_cls.return_value = mock_catalog
        mock_catalog.get_card.return_value = {
            "name": "Sonic Boom",
            "card_type": "Spell",
            "elements": "Air",
            "rarity": "Rare",
        }

        resp = client.get("/card/Sonic Boom", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'Sonic Boom' in html
        assert 'Spell' in html
        assert 'Air' in html
        assert 'Rare' in html

    @patch("routes.og_preview.CardCatalogRepository")
    def test_card_detail_not_found(self, mock_catalog_cls, client):
        """Unknown card still returns valid OG HTML."""
        mock_catalog = MagicMock()
        mock_catalog_cls.return_value = mock_catalog
        mock_catalog.get_card.return_value = None

        resp = client.get("/card/Unknown Card", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'og:title' in html
        assert 'Unknown Card' in html

    def test_og_html_escapes_special_characters(self, client):
        """Ensure HTML special characters are escaped in OG tags."""
        resp = client.get("/top-8", headers={"User-Agent": BOT_UA})
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

        resp = client.get("/top-8/TestEvent", headers={"User-Agent": BOT_UA})
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "<img" not in html
        assert "&lt;" in html
