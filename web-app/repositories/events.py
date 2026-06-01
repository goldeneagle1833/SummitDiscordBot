"""Repository for event/tournament data access from files."""

import json
import csv
import logging
import re
import shutil
import time
from pathlib import Path

from webapp_config import TOP_8_DIR, EVENT_RATINGS
from utils.formatting import format_event_name, extract_year_from_name

logger = logging.getLogger(__name__)


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

    def _find_json_files(self, event_folder: str) -> dict:
        """Find top8 and full JSON files for an event folder.

        Returns dict with 'top8' and 'full' keys (Path or None), or None if invalid.
        """
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

        return {"top8": top8_json, "full": full_json}

    def reorder_event_decks(
        self, event_folder: str, table_type: str, new_order: list[int]
    ) -> dict:
        """Reorder decks in a JSON file by rearranging the array.

        Args:
            event_folder: The event folder name.
            table_type: "top8" or "all" to select which JSON file.
            new_order: List of original indices in their new positions.

        Returns:
            dict with "success" bool and optional "error" string.
        """
        files = self._find_json_files(event_folder)
        if files is None:
            return {"success": False, "error": "Event not found"}

        if table_type == "top8":
            json_path = files["top8"]
        elif table_type == "all":
            json_path = files["full"]
        else:
            return {"success": False, "error": "Invalid table type"}

        if not json_path or not json_path.exists():
            return {"success": False, "error": f"No {table_type} JSON file found"}

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read {json_path}: {e}")
            return {"success": False, "error": "Failed to read JSON file"}

        # For top8, only reorder the first 8 entries
        if table_type == "top8":
            reorder_slice = data[:8]
            remainder = data[8:]
        else:
            reorder_slice = data
            remainder = []

        # Validate order array
        if len(new_order) != len(reorder_slice):
            return {
                "success": False,
                "error": f"Order length {len(new_order)} doesn't match deck count {len(reorder_slice)}",
            }

        if sorted(new_order) != list(range(len(reorder_slice))):
            return {
                "success": False,
                "error": "Invalid order: must contain each index exactly once",
            }

        # Apply reorder
        reordered = [reorder_slice[i] for i in new_order]
        new_data = reordered + remainder

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write {json_path}: {e}")
            return {"success": False, "error": "Failed to save reordered data"}

        return {"success": True}

    def _get_metadata_file(self) -> Path:
        """Get the path to the event metadata overrides JSON file."""
        return self._events_dir / "_event_metadata.json"

    def _load_metadata_overrides(self) -> dict:
        """Load saved event metadata overrides (name/rating), or empty dict."""
        meta_file = self._get_metadata_file()
        if not meta_file.exists():
            return {}
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def get_event_description(self, folder: str) -> str:
        """Get the description for an event, or empty string if none set."""
        overrides = self._load_metadata_overrides()
        return overrides.get(folder, {}).get("description", "")

    def update_event_metadata(self, folder: str, name: str | None = None, rating: int | None = None, description: str | None = None) -> dict:
        """Update display name, rating, and/or description for an event.

        Args:
            folder: The event folder name.
            name: New display name (or None to keep current).
            rating: New star rating 1-3 (or None to keep current).
            description: Event description text (or None to keep current).

        Returns:
            dict with "success" bool and optional "error" string.
        """
        overrides = self._load_metadata_overrides()
        entry = overrides.get(folder, {})

        if name is not None:
            entry["name"] = name
        if rating is not None:
            if not isinstance(rating, int) or rating < 1 or rating > 3:
                return {"success": False, "error": "Rating must be 1, 2, or 3"}
            entry["rating"] = rating
        if description is not None:
            entry["description"] = description

        overrides[folder] = entry

        try:
            with open(self._get_metadata_file(), "w", encoding="utf-8") as f:
                json.dump(overrides, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save event metadata: {e}")
            return {"success": False, "error": "Failed to save metadata"}

        return {"success": True}

    def _get_order_file(self) -> Path:
        """Get the path to the event order JSON file."""
        return self._events_dir / "_event_order.json"

    def _load_event_order(self) -> list[str] | None:
        """Load the saved event order (list of folder names), or None if not set."""
        order_file = self._get_order_file()
        if not order_file.exists():
            return None
        try:
            with open(order_file, "r", encoding="utf-8") as f:
                order = json.load(f)
            if isinstance(order, list):
                return order
        except Exception:
            pass
        return None

    def save_event_order(self, folder_order: list[str]) -> dict:
        """Save a custom event display order.

        Args:
            folder_order: List of event folder names in desired display order.

        Returns:
            dict with "success" bool and optional "error" string.
        """
        # Validate all entries are strings
        if not all(isinstance(f, str) for f in folder_order):
            return {"success": False, "error": "All entries must be strings"}

        try:
            with open(self._get_order_file(), "w", encoding="utf-8") as f:
                json.dump(folder_order, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save event order: {e}")
            return {"success": False, "error": "Failed to save event order"}

        return {"success": True}

    def get_all_events(self) -> list[dict]:
        """Get all events with their metadata."""
        events = []

        if not self._events_dir.exists():
            return events

        metadata_overrides = self._load_metadata_overrides()

        for folder in self._events_dir.iterdir():
            if not folder.is_dir():
                continue

            json_files = list(folder.glob("*.json"))
            top8_json = None
            full_json = None

            for json_file in json_files:
                if (
                    "top8" in json_file.name.lower()
                    or "top 8" in json_file.name.lower()
                ):
                    top8_json = json_file
                elif json_file.name.lower().startswith(folder.name.lower()):
                    full_json = json_file

            json_path = top8_json or full_json

            if json_path:
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        overrides = metadata_overrides.get(folder.name, {})
                        events.append(
                            {
                                "folder": folder.name,
                                "name": overrides.get("name", format_event_name(folder.name)),
                                "player_count": len(data),
                                "has_top8": top8_json is not None,
                                "has_full": full_json is not None,
                                "rating": overrides.get("rating", EVENT_RATINGS.get(folder.name, 1)),
                            }
                        )
                except Exception:
                    pass

        # Use saved custom order if available, otherwise sort by year
        saved_order = self._load_event_order()
        if saved_order:
            order_map = {name: i for i, name in enumerate(saved_order)}
            events.sort(key=lambda e: order_map.get(e["folder"], len(saved_order)))
        else:
            events.sort(
                key=lambda e: (
                    extract_year_from_name(e["name"]) > 0,
                    extract_year_from_name(e["name"]),
                ),
                reverse=True,
            )

        return events

    def get_recent_event(self, hours: int = 0) -> dict | None:
        """Get the latest event if it was added within the last N hours."""
        latest_file = self._events_dir / "latest_event.json"
        if not latest_file.exists():
            return None

        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        added_at = data.get("added_at", "")
        if not added_at:
            return None

        # Parse ISO timestamp and check if within the time window
        try:
            added_ts = time.mktime(time.strptime(added_at, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return None

        if time.time() - added_ts > hours * 3600:
            return None

        folder = data.get("folder", "")
        return {
            "folder": folder,
            "name": format_event_name(folder),
        }

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
                elif not any(
                    x in csv_file.name.lower() for x in ["element", "top8", "top 8"]
                ):
                    cards_csv = csv_file

            if elements_csv or cards_csv:
                events.append(
                    {
                        "folder": folder.name,
                        "name": format_event_name(folder.name),
                        "has_elements": elements_csv is not None,
                        "has_cards": cards_csv is not None,
                    }
                )

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
                        top8_decks.append(
                            {
                                "player": deck.get("username", "Unknown"),
                                "avatar": deck.get("avatar", [{}])[0].get(
                                    "name", "Unknown"
                                ),
                                "deck_name": deck.get("name", "Unnamed Deck"),
                                "deck_id": deck.get("id", ""),
                            }
                        )
            except Exception:
                pass

        if full_json and full_json != top8_json:
            try:
                with open(full_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for deck in data:
                        all_decks.append(
                            {
                                "player": deck.get("username", "Unknown"),
                                "avatar": deck.get("avatar", [{}])[0].get(
                                    "name", "Unknown"
                                ),
                                "deck_name": deck.get("name", "Unnamed Deck"),
                                "deck_id": deck.get("id", ""),
                            }
                        )
            except Exception:
                pass

        return {
            "top8_decks": top8_decks,
            "all_decks": all_decks,
        }

    def _load_all_decks(self, event_folder: str) -> list[dict] | None:
        """Load all deck JSON data for an event, combining top8 and full lists.

        Merges both files (deduplicating by deck ID) so element stats
        cover all decks in the event.
        """
        files = self._find_json_files(event_folder)
        if files is None:
            return None

        all_decks = []
        seen_ids = set()

        # Load top8 first
        if files["top8"] and files["top8"].exists():
            try:
                with open(files["top8"], "r", encoding="utf-8") as f:
                    for deck in json.load(f):
                        deck_id = deck.get("id", "")
                        all_decks.append(deck)
                        if deck_id:
                            seen_ids.add(deck_id)
            except Exception:
                pass

        # Add full/all participants, skipping duplicates
        if files["full"] and files["full"].exists() and files["full"] != files.get("top8"):
            try:
                with open(files["full"], "r", encoding="utf-8") as f:
                    for deck in json.load(f):
                        deck_id = deck.get("id", "")
                        if deck_id and deck_id in seen_ids:
                            continue
                        all_decks.append(deck)
                        if deck_id:
                            seen_ids.add(deck_id)
            except Exception:
                pass

        return all_decks if all_decks else None

    def get_event_element_stats(self, event_folder: str) -> dict | None:
        """Compute element presence and dominant element distribution from event deck data."""
        decks = self._load_all_decks(event_folder)
        if not decks:
            return None

        elements_order = ["Fire", "Water", "Earth", "Air"]
        presence_counts = {e: 0 for e in elements_order}
        dominant_counts = {e: 0 for e in elements_order}
        total_decks = len(decks)

        for deck in decks:
            spellbook = deck.get("spellbook", [])
            if not spellbook:
                continue

            # Track which elements appear and their total card quantity
            element_quantities = {e: 0 for e in elements_order}

            for card in spellbook:
                card_elements = card.get("elements", "None")
                quantity = card.get("quantity", 1)
                for el in card_elements.split(", "):
                    el = el.strip()
                    if el in element_quantities:
                        element_quantities[el] += quantity

            # Element presence: does this deck contain at least one card of each element?
            for el in elements_order:
                if element_quantities[el] > 0:
                    presence_counts[el] += 1

            # Dominant element: which element has the most cards?
            max_qty = max(element_quantities.values())
            if max_qty > 0:
                dominant = max(elements_order, key=lambda e: element_quantities[e])
                dominant_counts[dominant] += 1

        element_presence = []
        for el in elements_order:
            count = presence_counts[el]
            percent = round(count / total_decks * 100, 1) if total_decks else 0
            element_presence.append({"name": el, "count": count, "percent": percent})

        dominant_element = []
        for el in elements_order:
            count = dominant_counts[el]
            percent = round(count / total_decks * 100, 1) if total_decks else 0
            dominant_element.append({"name": el, "count": count, "percent": percent})

        return {
            "total_decks": total_decks,
            "element_presence": element_presence,
            "dominant_element": dominant_element,
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
            elif not any(
                x in csv_file.name.lower() for x in ["element", "top8", "top 8"]
            ):
                cards_csv = csv_file

        element_data = []
        card_data = []

        if elements_csv:
            try:
                with open(elements_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        element_data.append(
                            {
                                "elements": row.get("Deck Elements", "").strip(
                                    "\"()' "
                                ),
                                "count": row.get(" Count", row.get("Count", "0")),
                            }
                        )
            except Exception:
                pass

        if cards_csv:
            try:
                with open(cards_csv, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        count = int(row.get("Count", 0))
                        if count > 0:
                            card_data.append(
                                {
                                    "name": row.get("Name", "Unknown"),
                                    "type": row.get("Type", "Unknown"),
                                    "element": row.get("Element", "Unknown"),
                                    "count": count,
                                    "rarity": row.get("Rarity", "Unknown"),
                                    "avg_played": row.get("Average_Played", "0"),
                                    "deck_percent": row.get(
                                        "Percent_of_Decks_with_at_least_one_copy", "0"
                                    ),
                                }
                            )
                card_data.sort(key=lambda x: x["count"], reverse=True)
            except Exception:
                pass

        return {
            "element_data": element_data,
            "card_data": card_data,
        }

    def create_event(self, folder_name: str, top8_decks: list[dict], bulk_decks: list[dict] | None = None) -> dict:
        """Create a new event folder with deck JSON files.

        Args:
            folder_name: Name for the event folder.
            top8_decks: List of deck data dicts for the top 8 JSON file.
            bulk_decks: Optional list of additional deck data for the full event JSON file.

        Returns:
            dict with "success" bool and optional "error" string.
        """
        if not folder_name or not isinstance(folder_name, str):
            return {"success": False, "error": "Folder name is required"}

        if not self.SAFE_FOLDER_PATTERN.match(folder_name):
            return {"success": False, "error": "Folder name contains invalid characters"}

        event_path = self._events_dir / folder_name
        if event_path.exists():
            return {"success": False, "error": "An event with this name already exists"}

        try:
            event_path.mkdir(parents=True, exist_ok=False)
        except Exception as e:
            logger.error(f"Failed to create event directory: {e}")
            return {"success": False, "error": "Failed to create event directory"}

        # Write top8 JSON (the ranked placements)
        if top8_decks:
            top8_path = event_path / f"{folder_name}top8.json"
            try:
                with open(top8_path, "w", encoding="utf-8") as f:
                    json.dump(top8_decks, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to write top8 JSON: {e}")
                return {"success": False, "error": "Failed to write top 8 data"}

        # Write full event JSON only if there are bulk decks beyond the top 8
        # (no point duplicating top8 into all participants)
        if bulk_decks:
            full_path = event_path / f"{folder_name}.json"
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    json.dump(bulk_decks, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to write full event JSON: {e}")
                # top8 was already written, partial success

        # Generate card stats CSVs
        all_decks_for_stats = list(top8_decks) + (bulk_decks or [])
        if top8_decks:
            self.generate_card_stats_csv(folder_name, top8_decks, "top8")
        if all_decks_for_stats:
            self.generate_card_stats_csv(folder_name, all_decks_for_stats)

        # Write latest_event.json for the "recent event" banner
        try:
            latest_path = self._events_dir / "latest_event.json"
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump({
                    "folder": folder_name,
                    "added_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Non-critical

        return {"success": True, "folder": folder_name}

    def generate_card_stats_csv(self, event_folder: str, decks: list[dict], suffix: str = "") -> None:
        """Generate card usage statistics CSV from deck JSON data.

        Produces a CSV with columns matching the cardPercentages.py format:
        Name, Type, Element, Count, Rarity, Set, Average_Played, Percent_of_Decks_with_at_least_one_copy

        Args:
            event_folder: The event folder name.
            decks: List of deck data dicts (Curiosa format).
            suffix: Filename suffix, e.g. "top8" for top8-only stats.
        """
        event_path = self._validate_event_folder(event_folder)
        if event_path is None or not event_path.exists() or not decks:
            return

        total_decks = len(decks)
        # Collect card stats: {card_name: {type, element, rarity, set, total_qty, decks_with}}
        card_stats = {}

        for deck in decks:
            # Track which cards appear in this deck (for % of decks calculation)
            seen_in_deck = set()
            for group_name in ("avatar", "spellbook", "atlas"):
                group = deck.get(group_name, [])
                for card in group:
                    name = card.get("name", "")
                    if not name:
                        continue
                    qty = card.get("quantity", 1)

                    if name not in card_stats:
                        # Determine element - cards can have "elements" as string
                        elements = card.get("elements", "None")
                        card_stats[name] = {
                            "type": card.get("type", "Unknown"),
                            "element": elements,
                            "rarity": card.get("rarity", "Unknown"),
                            "set": "",
                            "total_qty": 0,
                            "decks_with": 0,
                        }

                    card_stats[name]["total_qty"] += qty
                    if name not in seen_in_deck:
                        card_stats[name]["decks_with"] += 1
                        seen_in_deck.add(name)

        # Build CSV rows
        rows = [["Name", "Type", "Element", "Count", "Rarity", "Set", "Average_Played",
                 "Percent_of_Decks_with_at_least_one_copy"]]

        for name, stats in sorted(card_stats.items()):
            decks_with = stats["decks_with"]
            avg_played = round(stats["total_qty"] / decks_with) if decks_with else 0
            deck_percent = round((decks_with / total_decks) * 100) if total_decks else 0
            rows.append([
                name,
                stats["type"],
                stats["element"],
                stats["total_qty"],
                stats["rarity"],
                stats["set"],
                avg_played,
                deck_percent,
            ])

        csv_name = f"{event_folder}{suffix}.csv"
        csv_path = event_path / csv_name
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
        except Exception as e:
            logger.error(f"Failed to write card stats CSV {csv_name}: {e}")

    def update_event_decks(self, event_folder: str, table_type: str, new_decks: list[dict], mode: str = "replace") -> dict:
        """Add or replace decks in an existing event's JSON file.

        Args:
            event_folder: The event folder name.
            table_type: "top8" or "all" to select which JSON file.
            new_decks: List of deck data dicts to add or replace with.
            mode: "replace" overwrites the file, "append" adds to existing decks.

        Returns:
            dict with "success" bool and optional "error" string.
        """
        event_path = self._validate_event_folder(event_folder)
        if event_path is None or not event_path.exists():
            return {"success": False, "error": "Event not found"}

        if table_type == "top8":
            json_path = event_path / f"{event_folder}top8.json"
        elif table_type == "all":
            json_path = event_path / f"{event_folder}.json"
        else:
            return {"success": False, "error": "Invalid table type"}

        if mode == "append" and json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, list):
                    new_decks = existing + new_decks
            except Exception:
                pass  # Fall through to write new_decks only

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(new_decks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write {table_type} JSON for {event_folder}: {e}")
            return {"success": False, "error": f"Failed to write {table_type} data"}

        # Regenerate card stats CSV for the updated list
        suffix = "top8" if table_type == "top8" else ""
        self.generate_card_stats_csv(event_folder, new_decks, suffix)

        return {"success": True}

    def delete_event(self, event_folder: str) -> dict:
        """Delete an event folder and all its contents.

        Also removes the event from metadata overrides and saved order.

        Args:
            event_folder: The event folder name.

        Returns:
            dict with "success" bool and optional "error" string.
        """
        event_path = self._validate_event_folder(event_folder)
        if event_path is None or not event_path.exists():
            return {"success": False, "error": "Event not found"}

        try:
            shutil.rmtree(event_path)
        except Exception as e:
            logger.error(f"Failed to delete event folder {event_folder}: {e}")
            return {"success": False, "error": "Failed to delete event folder"}

        # Remove from metadata overrides
        try:
            overrides = self._load_metadata_overrides()
            if event_folder in overrides:
                del overrides[event_folder]
                with open(self._get_metadata_file(), "w", encoding="utf-8") as f:
                    json.dump(overrides, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Non-critical

        # Remove from saved order
        try:
            saved_order = self._load_event_order()
            if saved_order and event_folder in saved_order:
                saved_order.remove(event_folder)
                with open(self._get_order_file(), "w", encoding="utf-8") as f:
                    json.dump(saved_order, f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Non-critical

        return {"success": True}

    def _refresh_json_file(self, json_path, curiosa_service, label: str) -> tuple[int, list[str]]:
        """Refresh decks in a single JSON file using batched Curiosa API calls.

        Returns (refreshed_count, error_list).
        """
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                old_decks = json.load(f)
        except Exception:
            old_decks = []

        if not old_decks:
            return 0, []

        # Collect deck IDs, preserving order
        deck_ids = []
        old_by_id = {}
        no_id_decks = []
        for deck in old_decks:
            deck_id = deck.get("id", "")
            if deck_id:
                deck_ids.append(deck_id)
                old_by_id[deck_id] = deck
            else:
                no_id_decks.append(deck)

        if not deck_ids:
            return 0, []

        fresh_decks, failed_ids = curiosa_service.fetch_decks_by_ids(deck_ids)
        fresh_by_id = {d.get("id"): d for d in fresh_decks}

        # Rebuild list in original order
        errors = []
        new_decks = []
        refreshed = 0
        for deck in old_decks:
            deck_id = deck.get("id", "")
            if not deck_id:
                new_decks.append(deck)
                continue
            if deck_id in fresh_by_id:
                new_decks.append(fresh_by_id[deck_id])
                refreshed += 1
            else:
                errors.append(f"Failed to refresh {label} deck: {deck.get('name', deck_id)}")
                new_decks.append(deck)  # Keep old data on failure

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(new_decks, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write refreshed {label}: {e}")
            errors.append(f"Failed to save refreshed {label} data")

        return refreshed, errors

    def refresh_event_decks(self, event_folder: str, curiosa_service) -> dict:
        """Re-fetch all deck data from Curiosa using stored deck IDs.

        Uses batched API calls to minimize request count and respect rate limits.

        Args:
            event_folder: The event folder name.
            curiosa_service: CuriosaService instance for API calls.

        Returns:
            dict with success, counts, and any errors.
        """
        files = self._find_json_files(event_folder)
        if files is None:
            return {"success": False, "error": "Event not found"}

        errors = []
        total_refreshed = 0

        # Refresh top8
        if files["top8"] and files["top8"].exists():
            count, errs = self._refresh_json_file(files["top8"], curiosa_service, "top 8")
            total_refreshed += count
            errors.extend(errs)
            if count > 0:
                try:
                    with open(files["top8"], "r", encoding="utf-8") as f:
                        self.generate_card_stats_csv(event_folder, json.load(f), "top8")
                except Exception:
                    pass

        # Refresh full/all
        if files["full"] and files["full"].exists():
            count, errs = self._refresh_json_file(files["full"], curiosa_service, "all participants")
            total_refreshed += count
            errors.extend(errs)
            if count > 0:
                try:
                    with open(files["full"], "r", encoding="utf-8") as f:
                        self.generate_card_stats_csv(event_folder, json.load(f))
                except Exception:
                    pass

        result = {"success": True, "refreshed": total_refreshed}
        if errors:
            result["warnings"] = errors
        return result
