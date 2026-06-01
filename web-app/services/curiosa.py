"""Curiosa API service for deck data."""

import json
import logging
import time
import requests

logger = logging.getLogger(__name__)

# Rate limit: minimum seconds between Curiosa API requests
CURIOSA_REQUEST_DELAY = 20

# Maximum deck IDs per batched API call
BATCH_SIZE = 10


class CuriosaService:
    """Service for interacting with Curiosa API."""

    BASE_URL = "https://curiosa.io/api"

    def __init__(self):
        self._last_request_time = 0

    def _rate_limit(self):
        """Wait if needed to respect the delay between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < CURIOSA_REQUEST_DELAY and self._last_request_time > 0:
            wait = CURIOSA_REQUEST_DELAY - elapsed
            logger.info(f"Rate limiting: waiting {wait:.1f}s before next Curiosa request")
            time.sleep(wait)
        self._last_request_time = time.time()

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

            self._rate_limit()
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

    def fetch_decks_batch(self, urls: list[str]) -> tuple[list[dict], list[str]]:
        """Fetch multiple decks in batched API calls (comma-separated IDs).

        Groups deck IDs into batches and makes one API call per batch,
        respecting the rate limit between batches.

        Args:
            urls: List of Curiosa deck URLs.

        Returns:
            Tuple of (list of deck dicts, list of error strings).
        """
        # Extract IDs, tracking which URL maps to which ID
        url_id_pairs = []
        errors = []
        for url in urls:
            if not url or not isinstance(url, str) or not url.strip():
                continue
            url = url.strip()
            deck_id = self.get_deck_id_from_url(url)
            if not deck_id:
                errors.append(f"Invalid URL: {url}")
                continue
            url_id_pairs.append((url, deck_id))

        if not url_id_pairs:
            return [], errors

        # Batch the IDs
        decks = []
        for i in range(0, len(url_id_pairs), BATCH_SIZE):
            batch = url_id_pairs[i:i + BATCH_SIZE]
            batch_ids = [pair[1] for pair in batch]
            batch_urls = {pair[1]: pair[0] for pair in batch}

            self._rate_limit()
            try:
                ids_param = ",".join(batch_ids)
                logger.info(f"Fetching batch of {len(batch_ids)} decks from Curiosa")
                response = requests.get(
                    f"{self.BASE_URL}/decks?ids={ids_param}",
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.warning(f"Curiosa API returned status {response.status_code} for batch")
                    for bid in batch_ids:
                        errors.append(f"API error (status {response.status_code}): {batch_urls[bid]}")
                    continue

                json_data = response.json()
                if not isinstance(json_data, list):
                    for bid in batch_ids:
                        errors.append(f"Invalid API response: {batch_urls[bid]}")
                    continue

                # Match returned decks to requested IDs
                returned_ids = {d.get("id") for d in json_data}
                for deck in json_data:
                    decks.append(deck)
                for bid in batch_ids:
                    if bid not in returned_ids:
                        errors.append(f"Deck not found: {batch_urls[bid]}")

            except requests.exceptions.Timeout:
                logger.warning("Curiosa API batch request timed out")
                for bid in batch_ids:
                    errors.append(f"Request timed out: {batch_urls[bid]}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Curiosa API batch request failed: {e}")
                for bid in batch_ids:
                    errors.append(f"Request failed: {batch_urls[bid]}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse Curiosa batch response: {e}")
                for bid in batch_ids:
                    errors.append(f"Parse error: {batch_urls[bid]}")

        return decks, errors

    def fetch_deck_by_id(self, deck_id: str) -> dict | None:
        """Fetch a single deck by its Curiosa ID. Returns deck dict or None."""
        try:
            self._rate_limit()
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

    def fetch_decks_by_ids(self, deck_ids: list[str]) -> tuple[list[dict], list[str]]:
        """Fetch multiple decks by ID in batched API calls.

        Args:
            deck_ids: List of Curiosa deck IDs.

        Returns:
            Tuple of (list of deck dicts, list of failed deck IDs).
        """
        decks = []
        failed = []

        for i in range(0, len(deck_ids), BATCH_SIZE):
            batch = deck_ids[i:i + BATCH_SIZE]
            self._rate_limit()
            try:
                ids_param = ",".join(batch)
                logger.info(f"Refreshing batch of {len(batch)} decks from Curiosa")
                response = requests.get(
                    f"{self.BASE_URL}/decks?ids={ids_param}",
                    timeout=30,
                )
                if response.status_code != 200:
                    logger.warning(f"Curiosa API returned status {response.status_code}")
                    failed.extend(batch)
                    continue

                data = response.json()
                if not isinstance(data, list):
                    failed.extend(batch)
                    continue

                returned_ids = {d.get("id") for d in data}
                decks.extend(data)
                for bid in batch:
                    if bid not in returned_ids:
                        failed.append(bid)

            except Exception as e:
                logger.warning(f"Batch fetch failed: {e}")
                failed.extend(batch)

        return decks, failed
