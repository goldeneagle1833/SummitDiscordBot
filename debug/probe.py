import json, re, requests
B = "https://sorcerytcg.com/api/trpc"
H = {"User-Agent": "Mozilla/5.0"}
EID = "cmvrgzj9w004x08l0myf1wpen"
def get(path, payload, label, n=1500):
    r = requests.get(f"{B}/{path}", params={"batch": "1", "input": json.dumps({"0": {"json": payload}})}, headers=H, timeout=60)
    print(f"== {label}: HTTP {r.status_code}, {len(r.content)} bytes")
    print(r.text[:n]); print(flush=True)
    return r
r = get("event.get", {"id": EID, "compact": True}, "compact", 300)
try:
    ev = r.json()[0]["result"]["data"]["json"]["event"]
    print("event keys:", sorted(ev.keys()))
    for k, v in ev.items():
        if isinstance(v, list) and v:
            print(f"list {k}: len {len(v)}; first item keys: {sorted(v[0].keys()) if isinstance(v[0], dict) else v[0]}")
            print(json.dumps(v[0])[:1200])
        elif isinstance(v, dict):
            print(f"dict {k}: {json.dumps(v)[:600]}")
except Exception as e:
    print("parse fail", e)
# find procedures in site JS
p = requests.get(f"https://sorcerytcg.com/events/{EID}", headers=H, timeout=60)
html = p.text
scripts = sorted(set(re.findall(r'/_next/static/[^"\'\s\\]+\.js', html)))
print("scripts", len(scripts))
procs = {}
for s in scripts:
    try:
        js = requests.get("https://sorcerytcg.com" + s, headers=H, timeout=30).text
    except Exception:
        continue
    for m in re.finditer(r'\b(event|round|pairing|registration|tournament|phase|standing)s?\.([a-zA-Z]+)\.(useQuery|useInfiniteQuery|useSuspenseQuery|query|fetch|prefetch)\b', js):
        key = f"{m.group(1)}.{m.group(2)}"
        if key not in procs:
            i = m.start()
            procs[key] = js[max(0, i-60): i+260].replace("\n", " ")
    for m in re.finditer(r'compact', js):
        i = m.start(); print("compact ctx:", s, js[max(0,i-300):i+200].replace("\n"," ")); 
for k, ctx in sorted(procs.items()):
    print("PROC", k, "::", ctx)
for path, payload in [
    ("event.rounds", {"eventId": EID}), ("event.pairings", {"eventId": EID}),
    ("event.round", {"eventId": EID, "number": 1}), ("event.matches", {"eventId": EID}),
    ("event.players", {"eventId": EID}), ("event.registrations", {"eventId": EID}),
    ("event.get", {"id": EID, "compact": False}),
]:
    get(path, payload, path, 600)
