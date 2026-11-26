"""sorcerytcg.com moved its event calls under "play." (2026-11-26).

play.getEvent replies {"event", "standings", "historyRevision"}; rounds carry
no pairings, so each round comes from play.getEventRound. Shapes copied from
the live CANADIAN GRAND CONTEST 2026 reply.
"""
import json
from unittest.mock import MagicMock, patch

from services.curiosa import CuriosaService
from services.explorer import ExplorerService, event_fetch_error_message, is_active_player

EID = "cmuv71j8c000006pbiub0gp7n"


def _resp(status, body):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


def _user(reg, name):
    return {"id": "u-" + reg, "displayname": name, "username": name.lower(),
            "feature": {"meta": {"image": f"https://img/{reg}.png"}}}


def _seat(reg, name, result, score):
    return {"registrationId": reg, "result": {"isBye": False, "score": score, "result": result},
            "registration": {"id": reg, "user": {"id": "u-" + reg, "displayname": name}}}


ROUNDS = {
    "r1": {"id": "r1", "number": 1, "pairings": [
        {"seats": [_seat("a", "Ann", "Loss", 0), _seat("b", "Bob", "Win", 3)]},
        {"seats": [_seat("c", "Cat", "Win", 3), _seat("d", "Dan", "Loss", 0)]},
    ]},
    "r2": {"id": "r2", "number": 2, "pairings": [
        {"seats": [_seat("a", "Ann", "Win", 3), _seat("c", "Cat", "Loss", 0)]},
    ]},
    "t1": {"id": "t1", "number": 3, "pairings": [
        {"seats": [_seat("a", "Ann", "Win", 3), _seat("b", "Bob", "Loss", 0)]},
    ]},
}


def _event_reply():
    event = {
        "id": EID, "title": "CANADIAN GRAND CONTEST 2026", "startsAt": "2026-10-10T14:15:00.000Z",
        "topcut": {"size": 2}, "store": {"name": "Tome2"},
        "players": [
            {"id": "a", "status": "Ready", "user": _user("a", "Ann"), "deck": None},
            {"id": "b", "status": "Ready", "user": _user("b", "Bob"), "deck": None},
            {"id": "c", "status": "Ready", "user": _user("c", "Cat"), "deck": None},
            {"id": "d", "status": "Dropped", "user": _user("d", "Dan"), "deck": None},
            {"id": "e", "status": "Dropped", "user": _user("e", "Eve"), "deck": None},
        ],
        "phases": [
            {"number": 1, "type": "Play", "structure": "Swiss", "format": "Constructed", "roundCount": 2,
             "rounds": [{"id": "r1", "number": 1}, {"id": "r2", "number": 2}]},
            {"number": 2, "type": "Play", "structure": "SingleElimination", "format": "Constructed",
             "roundCount": None, "rounds": [{"id": "t1", "number": 3}]},
        ],
    }
    standings = [
        {"id": "a", "position": 1, "score": 3, "wins": 2, "losses": 1, "draws": 0, "user": _user("a", "Ann")},
        {"id": "b", "position": 2, "score": 3, "wins": 1, "losses": 1, "draws": 0, "user": _user("b", "Bob")},
        {"id": "c", "position": 3, "score": 3, "wins": 1, "losses": 1, "draws": 0, "user": _user("c", "Cat")},
        {"id": "d", "position": 4, "score": 0, "wins": 0, "losses": 1, "draws": 0, "user": _user("d", "Dan")},
        {"id": "e", "position": 5, "score": 0, "wins": 0, "losses": 0, "draws": 0, "user": _user("e", "Eve")},
    ]
    return {"event": event, "standings": standings, "historyRevision": 0}


def _fake_get(url, params=None, timeout=None):
    path = url.rsplit("/", 1)[-1]
    inputs = json.loads(params["input"])
    if path == "play.getEvent":
        return _resp(200, [{"result": {"data": {"json": _event_reply()}}}])
    procs = path.split(",")
    if all(p == "play.getEventRound" for p in procs):
        out = []
        for j in range(len(procs)):
            inp = inputs[str(j)]["json"]
            assert inp["id"] == EID and inp["revision"] == 0
            out.append({"result": {"data": {"json": ROUNDS[inp["roundId"]]}}})
        return _resp(200, out)
    return _resp(404, [{"error": {"json": {"message": f'No procedure found on path "{path}"',
                                            "data": {"code": "NOT_FOUND"}}}}])


def test_importer_uses_play_procedures_and_rebuilds_history():
    with patch("services.explorer.requests.get", side_effect=_fake_get) as get, \
            patch.object(CuriosaService, "_fetch_page_html") as page:
        result = CuriosaService().fetch_event_deck_ids(
            f"https://sorcerytcg.com/events/{EID}", with_decks=False
        )
    page.assert_not_called()  # standings came from play.getEvent
    paths = [c.args[0].rsplit("/", 1)[-1] for c in get.call_args_list]
    assert paths[0] == "play.getEvent"
    assert all("event.get" not in p for p in paths)
    assert result["errors"] == []
    # Dan dropped after playing, Eve never played.
    assert result["player_count"] == 4
    history = {p["display_name"]: p for p in result["match_history"]}
    assert [history[n]["standing"] for n in ("Ann", "Bob", "Cat", "Dan")] == [1, 2, 3, 4]
    ann = history["Ann"]
    assert (ann["wins"], ann["losses"]) == (2, 1)
    assert [m["round"] for m in ann["matches"]] == [3, 2, 1]
    assert ann["matches"][0]["phase"] == "SingleElimination"
    assert ann["matches"][0]["opponent"]["display_name"] == "Bob"


def test_round_failure_keeps_import_and_says_so():
    def flaky(url, params=None, timeout=None):
        if "play.getEventRound" in url:
            return _resp(500, [{"error": {"json": {"message": "boom"}}}])
        return _fake_get(url, params, timeout)

    with patch("services.explorer.requests.get", side_effect=flaky), \
            patch.object(CuriosaService, "_fetch_page_html", return_value=""):
        result = CuriosaService().fetch_event_deck_ids(
            f"https://sorcerytcg.com/events/{EID}", with_decks=False
        )
    assert result["player_count"] == 4
    assert any("3 of 3 rounds" in e for e in result["errors"])


def test_explorer_standings_from_play_get_event():
    with patch("services.explorer.requests.get", side_effect=_fake_get), \
            patch.object(ExplorerService, "_fetch_page_html") as page:
        data = ExplorerService().fetch_event_data(f"https://sorcerytcg.com/events/{EID}")
    page.assert_not_called()
    assert data["standings_source"] == "official"
    assert [r["display_name"] for r in data["results"]] == ["Ann", "Bob", "Cat", "Dan"]
    assert data["results"][0]["wins"] == 2
    assert data["total_players"] == 4
    assert data["venue_name"] == "Tome2"


def test_player_counts_use_play_get_event_without_rounds():
    with patch("services.explorer.requests.get", side_effect=_fake_get) as get:
        rows = ExplorerService()._fetch_event_player_counts([{"id": EID, "startsAt": "2026-10-10"}])
    assert rows[0]["player_count"] == 4
    assert all("getEventRound" not in c.args[0] for c in get.call_args_list)


def test_active_player_counts_record():
    assert is_active_player({"status": "Dropped", "record": {"losses": 1}})
    assert not is_active_player({"status": "Dropped", "record": {"wins": 0, "losses": 0}})


def test_removed_procedure_message_blames_the_importer_not_the_link():
    msg = event_fetch_error_message(404, EID, 'NOT_FOUND: No procedure found on path "event.get"')
    assert "importer needs an update" in msg
    assert "Check the link" not in msg
