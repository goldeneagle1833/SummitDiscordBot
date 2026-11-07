"""Temporary read-only check of one public sorcerytcg.com event. Delete with this branch."""
import json, requests
EID = "cmw5zb6id001a08l53kccvck0"
B = "https://sorcerytcg.com/api/trpc"
def trpc(path, inp):
    r = requests.get(f"{B}/{path}", params={"batch": "1", "input": json.dumps({"0": {"json": inp}})}, timeout=30)
    return r.status_code, r.text
c, t = trpc("event.get", {"id": EID})
ev = json.loads(t)[0]["result"]["data"]["json"]["event"]
ps = ev.get("players", [])
for i, p in enumerate(ps[:4]):
    print(f"#{i} player.deck =", json.dumps(p.get("deck"))[:600])
    print("   user keys", list((p.get("user") or {}).keys()), (p.get("user") or {}).get("username"))
c, t = trpc("event.playerSnapshot", {"eventId": EID, "playerId": ps[0]["id"]})
snap = json.loads(t)[0]["result"]["data"]["json"]
print("snapshot name", snap.get("name"), "format", snap.get("format"), "frozen", json.dumps(snap.get("frozen"))[:300])
print("decklist entries", len(snap["decklist"]), "boards", sorted({e.get("board") for e in snap["decklist"]}))
print("entry keys", list(snap["decklist"][0].keys()), "printing keys", list((snap["decklist"][0].get("printing") or {}).keys()))
d = (ps[0].get("deck") or {})
did = d.get("id") if isinstance(d, dict) else d
if did:
    r = requests.get(f"{B}/deck.get", params={"input": json.dumps({"json": {"id": did}})}, timeout=30)
    print("deck.get on player.deck id", r.status_code, r.text[:400])
# older event that is known to import fine, for comparison
c, t = trpc("event.playerSnapshot", {"eventId": "cmt8a0tfd077i92cy1bb9wctz", "playerId": "x"})
print("old-event bogus snapshot", c, t[:200])
c, t = trpc("event.get", {"id": "cmt8a0tfd077i92cy1bb9wctz"})
old = json.loads(t)[0]["result"]["data"]["json"]["event"]
op = old["players"][0]
print("old player.deck =", json.dumps(op.get("deck"))[:300])
c, t = trpc("event.playerSnapshot", {"eventId": old["id"], "playerId": op["id"]})
os_ = json.loads(t)[0]["result"]["data"]["json"]
print("old snapshot keys", list(os_.keys()) if isinstance(os_, dict) else os_)
