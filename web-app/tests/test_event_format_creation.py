"""Regression tests for mandatory format when publishing tournament events."""

import json

import pytest

from repositories.events import EventRepository, EVENT_FORMATS
from routes.api.events import _required_event_format


@pytest.mark.parametrize("value", [None, "", "invalid", "Limited", 0, {}, []])
def test_required_format_rejects_missing_or_invalid(value):
    assert _required_event_format({"format": value}) is None


@pytest.mark.parametrize("value", ["Constructed", "Sealed", "Draft", "Peasant", "Unknown"])
def test_required_format_accepts_explicit_choice(value):
    assert value in EVENT_FORMATS
    assert _required_event_format({"format": value}) == value


@pytest.mark.parametrize("endpoint,payload", [
    ("/api/events/create", {
        "title": "Sample Grand Contest",
        "ranked_urls": ["https://sorcerytcg.com/decks/example"],
        "event_url": "https://sorcerytcg.com/events/example",
    }),
    ("/api/events/import-from-url", {"event_url": "https://sorcerytcg.com/events/example"}),
    ("/api/events/submissions/123/approve", {}),
])
@pytest.mark.parametrize("value", [None, "", "Limited", "NotAFormat"])
def test_admin_publish_endpoints_reject_missing_format(client, endpoint, payload, value):
    response = client.post(endpoint, json={**payload, "format": value},
                           headers={"X-API-Key": "test-api-key-123"})
    assert response.status_code == 400
    assert "format" in response.get_json()["error"].lower()


def test_new_event_persists_its_explicit_format(tmp_path):
    repo = EventRepository(tmp_path)
    result = repo.create_event("Special Event", [], event_format="Peasant")
    assert result["success"] is True
    metadata = json.loads((tmp_path / "_event_metadata.json").read_text())
    assert metadata["Special Event"]["format"] == "Peasant"


def test_legacy_internal_event_creation_does_not_write_a_format(tmp_path):
    repo = EventRepository(tmp_path)
    result = repo.create_event("Legacy Event", [])
    assert result["success"] is True
    assert not (tmp_path / "_event_metadata.json").exists()


def test_repository_does_not_create_invalid_format_event(tmp_path):
    repo = EventRepository(tmp_path)
    result = repo.create_event("Invalid Event", [], event_format="Limited")
    assert result["success"] is False
    assert not (tmp_path / "Invalid Event").exists()


# Regression coverage for the existing import jobs and submission test doubles.
# Admin HTTP endpoints continue to require an explicitly chosen format.
def test_optional_service_format_preserves_legacy_repository_interface():
    from routes.api.events import _create_event_with_optional_format

    class LegacyRepository:
        def create_event(self, folder, top8, bulk=None):
            return {"success": True, "folder": folder, "count": len(top8)}

    result = _create_event_with_optional_format(
        LegacyRepository(), "Legacy Event", [{}], None
    )
    assert result == {"success": True, "folder": "Legacy Event", "count": 1}


def test_explicit_service_format_is_persisted():
    from routes.api.events import _create_event_with_optional_format

    class FormatRepository:
        def create_event(self, folder, top8, bulk=None, *, event_format=None):
            return {"folder": folder, "format": event_format}

    result = _create_event_with_optional_format(
        FormatRepository(), "New Event", [{}], None, event_format="Sealed"
    )
    assert result == {"folder": "New Event", "format": "Sealed"}


def test_legacy_import_worker_still_accepts_its_old_signature():
    import inspect
    from routes.api.events import _run_event_import

    assert inspect.signature(_run_event_import).parameters["event_format"].default is None
