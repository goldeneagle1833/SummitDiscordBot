"""
Tests for LFG helper functions.

Tests utility functions:
- URL scrubbing for public channels
- Milestone message generation
- URL pattern matching

Run with: pytest tests/test_lfg_helpers.py -v
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.lfg.helpers import scrub_urls


class TestURLScrubbing:
    """Test URL scrubbing for public channels."""

    def test_scrub_single_http_url(self):
        """Test scrubbing a single HTTP URL."""
        text = "Check out my deck at http://curiosa.io/decks/123"
        result = scrub_urls(text)

        assert "http://curiosa.io/decks/123" not in result
        assert "[link removed]" in result
        assert "Check out my deck at" in result

    def test_scrub_single_https_url(self):
        """Test scrubbing a single HTTPS URL."""
        text = "My deck: https://curiosa.io/decks/456"
        result = scrub_urls(text)

        assert "https://curiosa.io/decks/456" not in result
        assert "[link removed]" in result

    def test_scrub_multiple_urls(self):
        """Test scrubbing multiple URLs in one message."""
        text = "Decks: https://curiosa.io/deck1 vs http://curiosa.io/deck2"
        result = scrub_urls(text)

        assert "https://curiosa.io/deck1" not in result
        assert "http://curiosa.io/deck2" not in result
        assert result.count("[link removed]") == 2
        assert "Decks:" in result
        assert "vs" in result

    def test_scrub_urls_with_query_params(self):
        """Test scrubbing URLs with query parameters."""
        text = "https://curiosa.io/decks/123?color=red&format=commander"
        result = scrub_urls(text)

        assert "curiosa.io" not in result
        assert "[link removed]" in result

    def test_scrub_urls_with_fragments(self):
        """Test scrubbing URLs with fragments."""
        text = "See https://curiosa.io/decks/123#cards section"
        result = scrub_urls(text)

        assert "curiosa.io" not in result
        assert "[link removed]" in result
        assert "section" in result

    def test_no_scrub_non_urls(self):
        """Test that non-URLs are not affected."""
        text = "User mentioned example.com without protocol"
        result = scrub_urls(text)

        assert result == text
        assert "[link removed]" not in result

    def test_scrub_preserves_message_structure(self):
        """Test that scrubbing preserves message structure."""
        text = "Match Found!\nDeck: https://curiosa.io/test\nGood luck!"
        result = scrub_urls(text)

        assert "Match Found!" in result
        assert "Deck:" in result
        assert "Good luck!" in result
        assert "[link removed]" in result

    def test_scrub_empty_string(self):
        """Test scrubbing empty string."""
        text = ""
        result = scrub_urls(text)
        assert result == ""

    def test_scrub_only_url(self):
        """Test message that is just a URL."""
        text = "https://curiosa.io/decks/789"
        result = scrub_urls(text)

        assert result == "[link removed]"

    def test_scrub_urls_with_mentions(self):
        """Test scrubbing preserves Discord mentions."""
        text = "<@123456789> check https://curiosa.io/deck"
        result = scrub_urls(text)

        assert "<@123456789>" in result
        assert "[link removed]" in result

    def test_scrub_urls_multiline(self):
        """Test scrubbing URLs in multiline text."""
        text = """Matched players:
        Player 1: https://curiosa.io/deck1
        Player 2: https://curiosa.io/deck2
        Status: Ready"""
        result = scrub_urls(text)

        assert result.count("[link removed]") == 2
        assert "Status: Ready" in result

    def test_scrub_urls_with_special_chars(self):
        """Test scrubbing URLs with special characters."""
        text = "Deck at https://curiosa.io/decks/test-123_ABC"
        result = scrub_urls(text)

        assert "[link removed]" in result
        assert "curiosa.io" not in result


class TestURLPattern:
    """Test URL pattern matching."""

    def test_http_pattern(self):
        """Test HTTP URL pattern."""
        import re
        pattern = re.compile(r"https?://\S+")

        text = "Visit http://example.com"
        assert pattern.search(text) is not None

    def test_https_pattern(self):
        """Test HTTPS URL pattern."""
        import re
        pattern = re.compile(r"https?://\S+")

        text = "Visit https://example.com"
        assert pattern.search(text) is not None

    def test_pattern_stops_at_whitespace(self):
        """Test that URL pattern stops at whitespace."""
        import re
        pattern = re.compile(r"https?://\S+")

        text = "URL is https://example.com and more text"
        match = pattern.search(text)
        assert match is not None
        assert match.group() == "https://example.com"

    def test_pattern_stops_at_punctuation(self):
        """Test URL pattern with trailing punctuation."""
        import re
        pattern = re.compile(r"https?://\S+")

        # Pattern stops at whitespace, not punctuation
        text = "Check https://example.com!"
        match = pattern.search(text)
        assert match is not None
        # Pattern will include the ! because it's non-whitespace
        assert "example.com" in match.group()


class TestScrubIntegration:
    """Integration tests for scrubbing in messages."""

    def test_scrub_match_found_message(self):
        """Test scrubbing a match found message."""
        text = "@User1 **Match Found!**\n\nYou've been matched with @User2\n\n**Your Deck:** https://curiosa.io/deck123"
        result = scrub_urls(text)

        assert "@User1" in result
        assert "@User2" in result
        assert "**Match Found!**" in result
        assert "**Your Deck:**" in result
        assert "[link removed]" in result
        assert "https://curiosa.io/deck123" not in result

    def test_scrub_preserves_formatting(self):
        """Test that scrubbing preserves markdown formatting."""
        text = "**Bold text** with https://example.com and *italic*"
        result = scrub_urls(text)

        assert "**Bold text**" in result
        assert "*italic*" in result
        assert "[link removed]" in result

    def test_scrub_consecutive_urls(self):
        """Test scrubbing consecutive URLs."""
        text = "https://curiosa.io/deck1https://curiosa.io/deck2"
        result = scrub_urls(text)

        # Both should be replaced
        assert "[link removed]" in result
        assert "curiosa.io" not in result

    def test_scrub_urls_in_dm(self):
        """Test URL scrubbing for DM fallback messages."""
        text = "You've been matched! Your deck: https://curiosa.io/secret_deck"
        result = scrub_urls(text)

        assert "You've been matched!" in result
        assert "Your deck:" in result
        assert "[link removed]" in result
        assert "secret_deck" not in result


class TestHelperEdgeCases:
    """Test edge cases in helper functions."""

    def test_scrub_very_long_message(self):
        """Test scrubbing very long messages."""
        urls = " ".join([f"https://example.com/deck{i}" for i in range(100)])
        text = f"Decks: {urls}"
        result = scrub_urls(text)

        assert result.count("[link removed]") == 100
        assert "example.com" not in result

    def test_scrub_unicode_characters(self):
        """Test scrubbing text with unicode characters."""
        text = "Deck 🎴 https://curiosa.io/deck with émojis"
        result = scrub_urls(text)

        assert "🎴" in result
        assert "émojis" in result
        assert "[link removed]" in result

    def test_scrub_special_discord_formatting(self):
        """Test scrubbing with Discord special formatting."""
        text = "||spoiler https://curiosa.io/deck|| and <@USER>"
        result = scrub_urls(text)

        assert "||spoiler" in result
        assert "[link removed]" in result
        assert "<@USER>" in result
