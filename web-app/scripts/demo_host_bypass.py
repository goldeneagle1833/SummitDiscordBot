"""Visual demo of the Host-header admin bypass in utils/auth.py.

Run from web-app/:
    python scripts/demo_host_bypass.py

Boots a minimal Flask app with one fake admin endpoint (`/admin-only`)
guarded by the real `require_admin` decorator from utils/auth.py.
Sends three requests via Flask's test client (no real network I/O):

  1. Normal request (no session, no Host trick)  -> expect 403
  2. Host: localhost                              -> with the bug, 200
  3. Host: 127.0.0.1                              -> with the bug, 200

Renders an HTML report at scripts/demo_host_bypass.html and opens it.
The same script run AFTER fixing utils/auth.py will show all three as 403,
making the fix visible at a glance.
"""

from __future__ import annotations

import html
import os
import sys
import webbrowser
from pathlib import Path

# Stub out env so webapp_config does not crash on missing prod values.
os.environ.setdefault("SECRET_KEY", "demo")
os.environ.setdefault("API_KEYS", "demo-api-key")
os.environ.setdefault("ADMIN_IDS", "demo_admin")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify
from utils.auth import require_admin


def build_app() -> Flask:
    app = Flask("host_bypass_demo")
    app.config["TESTING"] = True
    app.secret_key = "demo"

    @app.route("/admin-only")
    @require_admin
    def admin_only():
        return jsonify({"secret": "TOP SECRET ADMIN DATA"}), 200

    return app


CASES = [
    {
        "title": "1. Honest user (no session, normal Host)",
        "host": "sorcererssummit.com",
        "expected_safe": 403,
    },
    {
        "title": "2. Attacker sends  Host: localhost",
        "host": "localhost",
        "expected_safe": 403,
    },
    {
        "title": "3. Attacker sends  Host: 127.0.0.1",
        "host": "127.0.0.1",
        "expected_safe": 403,
    },
]


def run_cases(app: Flask) -> list[dict]:
    results = []
    client = app.test_client()
    for case in CASES:
        resp = client.get(
            "/admin-only",
            headers={"Host": case["host"]},
            environ_overrides={
                # Simulate a real external client IP (gunicorn-over-unix-socket
                # gives an empty string in prod; we mimic an attacker IP here so
                # the only thing that could possibly grant access is the Host header).
                "REMOTE_ADDR": "203.0.113.42",
            },
        )
        body = resp.get_data(as_text=True)
        results.append({
            **case,
            "status": resp.status_code,
            "body": body[:300],
            "vulnerable": resp.status_code == 200,
        })
    return results


HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Host Header Admin Bypass Demo</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 880px;
         margin: 40px auto; padding: 0 20px; color: #1a1a1a; }}
  h1 {{ margin-bottom: 4px; }}
  .sub {{ color: #666; margin-bottom: 24px; }}
  .case {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px 20px;
           margin-bottom: 16px; background: #fafafa; }}
  .case.vuln {{ border-color: #c62828; background: #fff5f5; }}
  .case.safe {{ border-color: #2e7d32; background: #f5fbf5; }}
  .case h3 {{ margin: 0 0 8px; }}
  .row {{ display: flex; gap: 16px; font-family: ui-monospace, monospace; font-size: 13px; }}
  .col {{ flex: 1; min-width: 0; }}
  .label {{ color: #888; font-size: 11px; text-transform: uppercase;
            letter-spacing: 0.5px; margin-bottom: 4px; }}
  pre {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 4px;
         padding: 8px 10px; margin: 0; overflow-x: auto; white-space: pre-wrap;
         word-break: break-all; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 12px; font-weight: 600; margin-left: 8px; }}
  .badge.vuln {{ background: #c62828; color: white; }}
  .badge.safe {{ background: #2e7d32; color: white; }}
  .summary {{ padding: 12px 16px; border-radius: 6px; margin-top: 16px; }}
  .summary.vuln {{ background: #ffebee; border: 1px solid #c62828; }}
  .summary.safe {{ background: #e8f5e9; border: 1px solid #2e7d32; }}
</style></head>
<body>
  <h1>Host Header Admin Bypass</h1>
  <div class="sub">
    Endpoint: <code>GET /admin-only</code> guarded by
    <code>@require_admin</code> from <code>utils/auth.py</code>.
    No session, no API key. Only the Host header is varied.
  </div>
  {cases}
  {summary}
</body></html>
"""

CASE_TEMPLATE = """
  <div class="case {cls}">
    <h3>{title} <span class="badge {cls}">{verdict}</span></h3>
    <div class="row">
      <div class="col">
        <div class="label">Request</div>
        <pre>GET /admin-only HTTP/1.1
Host: {host}
X-Real-Client: 203.0.113.42</pre>
      </div>
      <div class="col">
        <div class="label">Response — HTTP {status}</div>
        <pre>{body}</pre>
      </div>
    </div>
  </div>
"""


def render(results: list[dict], out_path: Path) -> None:
    any_vuln = any(r["vulnerable"] for r in results)

    cases_html = "".join(
        CASE_TEMPLATE.format(
            cls="vuln" if r["vulnerable"] else "safe",
            verdict="BYPASSED" if r["vulnerable"] else "BLOCKED",
            title=html.escape(r["title"]),
            host=html.escape(r["host"]),
            status=r["status"],
            body=html.escape(r["body"] or "(empty)"),
        )
        for r in results
    )

    if any_vuln:
        summary = (
            '<div class="summary vuln"><strong>Vulnerable.</strong> '
            "At least one request reached admin-only data without a "
            "session or API key. The fix is in <code>utils/auth.py</code>: "
            "remove the <code>host.startswith(...)</code> branch.</div>"
        )
    else:
        summary = (
            '<div class="summary safe"><strong>Fixed.</strong> '
            "All Host-header variants now return 403.</div>"
        )

    out_path.write_text(
        HTML_TEMPLATE.format(cases=cases_html, summary=summary),
        encoding="utf-8",
    )


def main() -> int:
    app = build_app()
    results = run_cases(app)

    out = Path(__file__).resolve().parent / "demo_host_bypass.html"
    render(results, out)

    print()
    for r in results:
        marker = "BYPASSED" if r["vulnerable"] else "blocked"
        print(f"  [{r['status']}] Host={r['host']:<25} -> {marker}")
    print(f"\n  Report: {out}")

    webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
