"""Read-only live check of the fixed importer against sorcerytcg.com."""
import json, sys, logging
sys.path.insert(0, "web-app")
logging.basicConfig(level=logging.WARNING)
from services.curiosa import CuriosaService
from services.explorer import ExplorerService
for eid in ["cmuv71j8c000006pbiub0gp7n", "cmw5zb6id001a08l53kccvck0", "cmvrgzj9w004x08l0myf1wpen"]:
    url = f"https://sorcerytcg.com/events/{eid}"
    print("=" * 20, eid)
    try:
        r = CuriosaService().fetch_event_deck_ids(url)
    except Exception as e:
        print("IMPORT FAIL", type(e).__name__, e); continue
    print("NAME", r["event_name"], r["event_date"], "topcut", r["top_cut_size"], "players", r["player_count"])
    print("DECKS", len(r["players"]), "ERRORS", len(r["errors"]), r["errors"][:5])
    for p in r["players"][:3]:
        d = p.get("deck") or {}
        print("  DECK", p["standing"], p["name"], p["deck_id"], "avatar" , json.dumps(d)[:300])
    mh = r["match_history"]
    print("HISTORY players", len(mh), "rows", sum(len(p["matches"]) for p in mh))
    for p in mh[:3]:
        print("  H", p["standing"], p["display_name"], p["wins"], p["losses"], p["draws"], [(m["round"], m["result"], (m["opponent"] or {}).get("display_name")) for m in p["matches"]][:4])
    try:
        d = ExplorerService().fetch_event_data(url)
        print("EXPLORER", d["event_name"], d["total_players"], d["standings_source"], d["top_cut_size"], [(x["final_standing"], x["display_name"], x["wins"]) for x in d["results"][:4]])
    except Exception as e:
        print("EXPLORER FAIL", e)
try:
    v = ExplorerService().fetch_venue_attendance("https://sorcerytcg.com/stores/cmt871kzx00u02wcyno7bkwrh")
    print("VENUE", v["store_name"], len(v["events"]), v["events"][-3:])
except Exception as e:
    print("VENUE FAIL", e)
