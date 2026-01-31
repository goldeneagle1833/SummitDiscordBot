"""Repository for event/tournament data access from files."""

import json
import csv
import re
from pathlib import Path

from webapp_config import TOP_8_DIR, EVENT_RATINGS
from utils.formatting import format_event_name, extract_year_from_name


class EventRepository:
    """Data access for event JSON/CSV files."""

    # Safe pattern: alphanumeric, spaces, hyphens, underscores, apostrophes
    SAFE_FOLDER_PATTERN = re.compile(r"^[a-zA-Z0-9 _\-']+$")

    def __init__(self, events_dir: Path | None = None):
        self._events_dir = events_dir or TOP_8_DIR

    def _validate_event_folder(self, event_folder: str) -> Path | None:
        """
        Validate event_folder to prevent path traversal attacks.
        Returns the safe path if valid, None otherwise.
        """
        # Reject empty or obviously malicious input
        if not event_folder or not isinstance(event_folder, str):
            return None

        # Reject path traversal attempts
        if ".." in event_folder or "/" in event_folder or "\\" in event_folder:
            return None

        # Only allow safe characters
        if not self.SAFE_FOLDER_PATTERN.match(event_folder):
            return None

        # Construct and resolve the path
        event_path = (self._events_dir / event_folder).resolve()

        # Verify the resolved path is still within the events directory
        try:
            event_path.relative_to(self._events_dir.resolve())
        except ValueError:
            # Path escaped the events directory
            return None

        return event_path

    def get_all_events(self) -> list[dict]:
        """Get all events with their metadata."""
        events = []

        if not self._events_dir.exists():
            return events

        for folder in self._events_dir.iterdir():
            if not folder.is_dir():
                continue

            json_files = list(folder.glob("*.json"))
            top8_json = None
            full_json = None

            for json_file in json_files:
                if "top8" in json_file.name.lower() or "top 8" in json_file.name.lower():
                    top8_json = json_file
                elif json_file.name.lower().startswith(folder.name.lower()):
                    full_json = json_file

            json_path = top8_json or full_json

            if json_path:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        events.append({
                            "folder": folder.name,
                            "name": format_event_name(folder.name),
                            "player_count": len(data),
                            "has_top8": top8_json is not None,
                            "has_full": full_json is not None,
                            "rating": EVENT_RATINGS.get(folder.name, 1),
                        })
                except Exception:
                    pass

        # Sort by year descending
        events.sort(
            key=lambda e: (
                extract_year_from_name(e["name"]) > 0,
                extract_year_from_name(e["name"]),
            ),
            reverse=True,
        )

        return events

    def get_events_with_stats(self) -> list[dict]:
        """Get events that have CSV statistics files."""
        events = []

        if not self._events_dir.exists():
            return events

        for folder in self._events_dir.iterdir():
            if not folder.is_dir():
                continue

            csv_files = list(folder.glob("*.csv"))
            elements_csv = None
            cards_csv = None

            for csv_file in csv_files:
                if "element" in csv_file.name.lower():
                    elements_csv = csv_file
                elif not any(x in csv_file.name.lower() for x in ["element", "top8", "top 8"]):
                    cards_csv = csv_file

            if elements_csv or cards_csv:
                events.append({
                    "folder": folder.name,
                    "name": format_event_name(folder.name),
                    "has_elements": elements_csv is not None,
                    "has_cards": cards_csv is not None,
                })

        events.sort(
            key=lambda e: (
                extract_year_from_name(e["name"]) > 0,
                extract_year_from_name(e["name"]),
            ),
            reverse=True,
        )

        return events

    def get_event_decks(self, event_folder: str) -> dict:
        """Get deck data for a specific event."""
        event_path = self._validate_event_folder(event_folder)

        if event_path is None or not event_path.exists():
            return None

        json_files = list(event_path.glob("*.json"))
        top8_json = None
        full_json = None

        for json_file in json_files:
            if "top8" in json_file.name.lower() or "top 8" in json_file.name.lower():
                top8_json = json_file
            elif json_file.name.lower().startswith(event_folder.lower()):
                full_json = json_file

        top8_decks = []
        all_decks = []

        if top8_json:
            try:
                with open(top8_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for deck in data[:8]:
                        top8_decks.append({
                            "player": deck.get("username", "Unknown"),
                            "avatar": deck.get("avatar", [{}])[0].get("name", "Unknown"),
                            "deck_name": deck.get("name", "Unnamed Deck"),
                            "deck_id": deck.get("id", ""),
                        })
            except Exception:
                pass

        if full_json and full_json != top8_json:
            try:
                with open(full_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for deck in data:
                        all_decks.append({
                            "player": deck.get("username", "Unknown"),
                            "avatar": deck.get("avatar", [{}])[0].get("name", "Unknown"),
                            "deck_name": deck.get("name", "Unnamed Deck"),
                            "deck_id": deck.get("id", ""),
                        })
            except Exception:
                pass

        return {
            "top8_decks": top8_decks,
            "all_decks": all_decks,
        }

    def get_event_stats(self, event_folder: str) -> dict:
        """Get statistics data for a specific event."""
        event_path = self._validate_event_folder(event_folder)

        if event_path is None or not event_path.exists():
            return None

        csv_files = list(event_path.glob("*.csv"))
        elements_csv = None
        cards_csv = None

        for csv_file in csv_files:
            if "element" in csv_file.name.lower():
                elements_csv = csv_file
            elif not any(x in csv_file.name.lower() for x in ["element", "top8", "top 8"]):
                cards_csv = csv_file

        element_data = []
        card_data = []

        if elements_csv:
            try:
                with open(elements_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        element_data.append({
                            "elements": row.get("Deck Elements", "").strip("\"()' "),
                            "count": row.get(" Count", row.get("Count", "0")),
                        })
            except Exception:
                pass

        if cards_csv:
            try:
                with open(cards_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        count = int(row.get("Count", 0))
                        if count > 0:
                            card_data.append({
                                "name": row.get("Name", "Unknown"),
                                "type": row.get("Type", "Unknown"),
                                "element": row.get("Element", "Unknown"),
                                "count": count,
                                "rarity": row.get("Rarity", "Unknown"),
                                "avg_played": row.get("Average_Played", "0"),
                                "deck_percent": row.get(
                                    "Percent_of_Decks_with_at_least_one_copy", "0"
                                ),
                            })
                card_data.sort(key=lambda x: x["count"], reverse=True)
            except Exception:
                pass

        return {
            "element_data": element_data,
            "card_data": card_data,
        }
