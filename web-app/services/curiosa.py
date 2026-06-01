"""Curiosa API service for deck data."""

import json
import logging
import requests

logger = logging.getLogger(__name__)


class CuriosaService:
    """Service for interacting with Curiosa API."""

    BASE_URL = "https://curiosa.io/api"

    def get_deck_id_from_url(self, url: str) -> str:
        """Extract deck ID from Curiosa URL."""
        base_url = url.split("?")[0]
        deck_id = base_url.rstrip("/").split("/")[-1]
        return deck_id

    def fetch_deck_data(self, deck_url: str) -> str:
        """
        Fetch deck data from Curiosa API.
        Returns JSON string of deck data, or '{}' on failure.
        """
        try:
            deck_id = self.get_deck_id_from_url(deck_url)
            if not deck_id:
                logger.warning("Could not extract deck ID from URL")
                return "{}"

            response = requests.get(
                f"{self.BASE_URL}/decks?ids={deck_id}",
                timeout=30,
            )

            if response.status_code != 200:
                logger.warning(f"Curiosa API returned status {response.status_code}")
                return "{}"

            json_data = response.json()

            if not isinstance(json_data, list) or len(json_data) == 0:
                logger.warning("Curiosa API did not return valid deck data")
                return "{}"

            return json.dumps(json_data[0])

        except requests.exceptions.Timeout:
            logger.warning("Curiosa API request timed out")
            return "{}"
        except requests.exceptions.RequestException as e:
            logger.warning(f"Curiosa API request failed: {e}")
            return "{}"
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            logger.warning(f"Failed to parse Curiosa response: {e}")
            return "{}"

    def fetch_deck_by_id(self, deck_id: str) -> dict | None:
        """Fetch a single deck by its Curiosa ID. Returns deck dict or None."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/decks?ids={deck_id}",
                timeout=30,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
        except Exception as e:
            logger.warning(f"Failed to fetch deck {deck_id}: {e}")
        return None
