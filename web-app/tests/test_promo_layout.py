"""Admin > Home Promos: carousel order and on/off settings."""
from repositories.analytics import AnalyticsRepository


def _banner(title, active=True):
    repo = AnalyticsRepository()
    bid = repo.create_banner(title=title, link="/x", expires_at="2999-01-01 00:00:00")
    if not active:
        repo.set_banner_active(bid, False)
    return bid


def test_active_banners_carry_empty_layout_by_default(client):
    _banner("One")
    d = client.get("/api/analytics/banners/active").get_json()
    assert d["success"]
    assert set(d["layout"]) == {"order", "hidden"}


def test_layout_needs_admin(client, user_session):
    assert client.get("/api/analytics/promo-layout").status_code in (401, 403)
    r = client.post("/api/analytics/promo-layout", json={"order": [], "off": []})
    assert r.status_code in (401, 403)


def test_save_order_and_off(admin_session):
    a = _banner("A")
    b = _banner("B")
    expired = AnalyticsRepository().create_banner(title="Old", link="/o", expires_at="2000-01-01 00:00:00")

    order = [f"promo-{b}", "staff-pick", "kudos", f"promo-{a}"]
    r = admin_session.post("/api/analytics/promo-layout",
                           json={"order": order, "off": ["kudos", f"promo-{a}"]})
    assert r.get_json()["success"]

    d = admin_session.get("/api/analytics/promo-layout").get_json()
    assert d["layout"]["order"] == order
    assert d["layout"]["hidden"] == ["kudos"]  # banners use their own on/off flag
    by_id = {x["id"]: x for x in d["banners"]}
    assert by_id[a]["active"] is False and by_id[b]["active"] is True
    assert expired not in by_id  # expired banners are not listed

    # The public list drops the banner that was turned off
    live = admin_session.get("/api/analytics/banners/active").get_json()
    ids = {x["id"] for x in live["banners"]}  # the analytics db is shared across tests
    assert b in ids and a not in ids
    assert live["layout"]["order"] == order

    # Turning it back on works
    admin_session.post("/api/analytics/promo-layout", json={"order": order, "off": []})
    live = admin_session.get("/api/analytics/banners/active").get_json()
    assert {a, b} <= {x["id"] for x in live["banners"]}
    assert live["layout"]["hidden"] == []


def test_rejects_bad_slot_names(admin_session):
    r = admin_session.post("/api/analytics/promo-layout", json={"order": ["<script>"], "off": []})
    assert r.status_code == 400
    r = admin_session.post("/api/analytics/promo-layout", json={"order": "kudos"})
    assert r.status_code == 400
