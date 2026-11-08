"""Temporary read-only run of the fixed importer discovery against one public event."""
import sys
sys.path.insert(0, "web-app")
from services.curiosa import CuriosaService
r = CuriosaService().fetch_event_deck_ids("https://sorcerytcg.com/events/cmw5zb6id001a08l53kccvck0", on_progress=print)
print("event", r["event_name"], "top cut", r["top_cut_size"], "errors", r["errors"])
for p in r["players"]:
    d = p.get("deck") or {}
    n = lambda k: sum(c.get("quantity", 1) for c in d.get(k, []))
    print(p["standing"], p["name"], "|", d.get("name"), "| avatar", [c["name"] for c in d.get("avatar", [])],
          "spellbook", n("spellbook"), "atlas", n("atlas"), "collection", n("sideboard"))
print("history players", len(r["match_history"]), "with deck ids", sum(1 for h in r["match_history"] if h["deck_id"]))
