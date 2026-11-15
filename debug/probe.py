import sys, collections
sys.path.insert(0, "web-app")
from services.curiosa import CuriosaService
from services.explorer import ExplorerService
URL = "https://sorcerytcg.com/events/cmvrgzj9w004x08l0myf1wpen"
r = CuriosaService().fetch_event_deck_ids(URL, with_decks=True)
print("event", r["event_name"], r["event_date"], "players", r["player_count"], "decks", len(r["players"]), "errors", len(r["errors"]), r["errors"][:5])
h = r["match_history"]
print("history players", len(h), "with matches", sum(1 for p in h if p["matches"]))
print("total match rows", sum(len(p["matches"]) for p in h))
print("rounds seen", sorted(collections.Counter(m["round"] for p in h for m in p["matches"]).items()))
print("phases", collections.Counter(m["phase"] for p in h for m in p["matches"]))
for p in h[:8]:
    print(p["standing"], p["display_name"], f'{p["wins"]}-{p["losses"]}-{p["draws"]}', [(m["round"], m["result"], (m["opponent"] or {}).get("display_name")) for m in p["matches"][:4]])
no_opp = sum(1 for p in h for m in p["matches"] if not m["opponent"] and not m["is_bye"])
print("non-bye matches without opponent", no_opp)
e = ExplorerService().fetch_event_data(URL)
print("explorer total_players", e["total_players"], "standings_source", e["standings_source"], "unmatched", len(e["unmatched_players"]))
print("top 4", [(x.get("display_name"), x.get("standing"), x.get("wins"), x.get("losses")) for x in e["results"][:4]])
