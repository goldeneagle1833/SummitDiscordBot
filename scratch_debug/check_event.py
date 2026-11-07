"""Temporary read-only check of one public sorcerytcg.com event. Delete with this branch."""
import json, sys, requests
EID = "cmw5zb6id001a08l53kccvck0"
B = "https://sorcerytcg.com/api/trpc"
def trpc(path, inp):
    r = requests.get(f"{B}/{path}", params={"batch": "1", "input": json.dumps({"0": {"json": inp}})}, timeout=30)
    return r.status_code, r.text
c, t = trpc("event.get", {"id": EID})
print("event.get", c, len(t))
if c != 200:
    print(t[:3000]); sys.exit()
ev = json.loads(t)[0]["result"]["data"]["json"]["event"]
print("keys", list(ev.keys()))
for k, v in ev.items():
    if not isinstance(v, (list, dict)):
        print(" ", k, "=", v)
    elif isinstance(v, dict):
        print(" ", k, "= dict", list(v.keys())[:20])
ps = ev.get("players", [])
print("players", len(ps))
if ps:
    print("player keys", list(ps[0].keys()))
    print("player[0] scalars", {k: v for k, v in ps[0].items() if not isinstance(v, (list, dict))})
for i, p in enumerate(ps):
    c, t = trpc("event.playerSnapshot", {"eventId": EID, "playerId": p["id"]})
    try:
        body = json.loads(t)[0]
    except Exception:
        body = None
    snap = (((body or {}).get("result") or {}).get("data") or {}).get("json")
    sd = (snap or {}).get("sourceDeck") if isinstance(snap, dict) else None
    print(f"#{i} status={p.get('status')} seats={len(p.get('seats') or [])} snap_http={c} snap_type={type(snap).__name__} "
          f"snap_keys={list(snap.keys()) if isinstance(snap, dict) else None} sourceDeck={'id' if sd and sd.get('id') else sd}")
    if i < 2 or c != 200:
        print("   raw:", t[:1500])
    if sd and sd.get("id"):
        r = requests.get(f"{B}/deck.get", params={"input": json.dumps({"json": {"id": sd["id"]}})}, timeout=30)
        print("   deck.get", r.status_code, r.text[:300] if r.status_code != 200 else "ok")
