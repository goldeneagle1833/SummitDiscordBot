"""Tests for the Store Admin sales dashboard and monthly sales CSV."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from repositories.store import StoreRepository
from services.store_dashboard import StoreDashboard

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
ADDRESS = {"name": "T", "line1": "1 Main", "city": "Columbus", "state": "OH",
           "postal": "43201", "country": "US"}


def _ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def repo(tmp_path):
    return StoreRepository(db_path=tmp_path / "store.db")


def _sale(repo, product_id, user="u1", qty=1, paid_days_ago=1, status="paid",
          shipped_days_ago=None, created_days_ago=None):
    order = repo.create_order(user_id=user, username=user.upper(),
                              items=[{"product_id": product_id, "quantity": qty}],
                              shipping_address=ADDRESS, shipping_cents=300)
    created = _ts(created_days_ago if created_days_ago is not None else paid_days_ago)
    with repo._connect() as conn:
        conn.execute(
            "UPDATE orders SET status = ?, created_at = ?, paid_at = ?, shipped_at = ? WHERE id = ?",
            (status, created, None if status == "cancelled" else _ts(paid_days_ago),
             _ts(shipped_days_ago) if shipped_days_ago is not None else None, order["id"]),
        )
    return order


@pytest.fixture()
def shop(repo):
    explorer = repo.create_storefront("explorer", "Explorer Store")
    token = repo.create_product(sku="TOK", name="Token", price_cents=500, stock_quantity=100)
    mat = repo.create_product(sku="MAT", name="Playmat", price_cents=2500, stock_quantity=2)
    pin = repo.create_product(sku="PIN", name="Pin", price_cents=1000, stock_quantity=50,
                              storefront_id=explorer)
    _sale(repo, token, "u1", qty=2, paid_days_ago=3, status="shipped", shipped_days_ago=2)  # 1300
    _sale(repo, token, "u1", qty=1, paid_days_ago=5, status="delivered", shipped_days_ago=1)  # 800
    _sale(repo, mat, "u2", paid_days_ago=2)  # 2800, still to ship
    _sale(repo, token, "u3", paid_days_ago=40, status="shipped", shipped_days_ago=39)  # previous period
    _sale(repo, mat, "u4", paid_days_ago=4, status="refunded")
    _sale(repo, token, "u5", status="cancelled", created_days_ago=2)  # unfinished checkout
    _sale(repo, pin, "u1", paid_days_ago=1)  # other storefront
    repo.update_product(token, max_per_user_monthly=2)  # cap set after the sales
    return {"summit": repo.default_storefront_id(), "explorer": explorer,
            "token": token, "mat": mat, "pin": pin}


def _summary(repo, ids, days=30):
    return StoreDashboard(repo).summary(ids, days, now=NOW)


class TestDashboard:
    def test_totals_and_previous_period(self, repo, shop):
        d = _summary(repo, [shop["summit"]])
        assert d["totals"] == {"sales_cents": 4900, "orders": 3, "units": 4, "average_cents": 1633}
        assert d["previous"]["orders"] == 1

    def test_scope_limits_everything(self, repo, shop):
        d = _summary(repo, [shop["explorer"]])
        assert d["totals"]["orders"] == 1
        assert [p["name"] for p in d["top_products"]] == ["Pin"]
        assert _summary(repo, [])["totals"]["orders"] == 0
        assert _summary(repo, None)["totals"]["orders"] == 4

    def test_daily_series_covers_every_day(self, repo, shop):
        d = _summary(repo, [shop["summit"]], days=7)
        assert len(d["daily"]) == 7
        assert d["daily"][-1]["date"] == "2026-10-12"
        by_day = {x["date"]: x for x in d["daily"]}
        assert by_day["2026-10-10"]["sales_cents"] == 2800
        assert by_day["2026-10-10"]["unfinished_cents"] == 800

    def test_attention(self, repo, shop):
        a = _summary(repo, [shop["summit"]])["attention"]
        assert a["to_ship"] == 1
        assert a["unfinished_week"] == 1
        assert [p["name"] for p in a["low_stock"]] == ["Playmat"]

    def test_money_and_refunds(self, repo, shop):
        m = _summary(repo, [shop["summit"]])["money"]
        assert m["products_cents"] == 4000
        assert m["shipping_cents"] == 900
        assert m["refunded_cents"] == 2800 and m["refunded_orders"] == 1

    def test_repeat_buyers(self, repo, shop):
        r = _summary(repo, [shop["summit"]])["repeat_buyers"]
        assert r["buyers"] == 2 and r["repeat"] == 1
        assert r["best"][0]["username"] == "U2"

    def test_ship_time(self, repo, shop):
        t = _summary(repo, [shop["summit"]])["ship_time"]
        assert t["shipped"] == 2
        assert t["average_hours"] == 60.0  # 24h and 96h
        assert t["within_2_days"] == 1

    def test_limit_hits(self, repo, shop):
        hits = _summary(repo, [shop["summit"]])["limit_hits"]
        token = next(h for h in hits if h["name"] == "Token")
        assert token["cap"] == 2
        assert token["hits"] == 1  # u1 bought 3 in October
        assert token["buyers"] == 1  # the cancelled checkout doesn't count

    def test_flagged_payments_follow_scope(self, repo, shop):
        order = repo.get_order(1)
        repo.log_action("stripe-webhook", "system", "amount_mismatch",
                        f"order={order['order_number']} expected=1 got=2")
        assert StoreDashboard(repo)._flagged(repo._connect(), [shop["summit"]],
                                             datetime.now(timezone.utc)) == 1
        assert StoreDashboard(repo)._flagged(repo._connect(), [shop["explorer"]],
                                             datetime.now(timezone.utc)) == 0

    def test_states(self, repo, shop):
        states = _summary(repo, [shop["summit"]])["states"]
        assert states == [{"state": "OH", "orders": 3, "sales_cents": 4900}]

    def test_order_map_groups_by_city_and_uses_cache(self, repo, shop):
        dash = StoreDashboard(repo)
        m = dash.order_map([shop["summit"]], 30, now=NOW, geocode=False)
        assert m["places"] == [] and m["locating"] == 1
        with repo._connect() as conn:
            dash._ensure_geo_cache(conn)
            conn.execute("INSERT INTO geo_cache VALUES (?, 39.96, -83.0, ?)",
                         (dash._geo_key(" Columbus ", "oh"), NOW.isoformat()))
        m = dash.order_map([shop["summit"]], 30, now=NOW, geocode=False)
        assert m["locating"] == 0
        assert m["places"] == [{"city": "Columbus", "state": "OH", "orders": 3,
                                "sales_cents": 4900, "latitude": 39.96, "longitude": -83.0}]
        assert dash.order_map([shop["explorer"]], 7, now=NOW, geocode=False)["places"][0]["orders"] == 1

    def test_order_map_geocodes_missing_cities_once(self, repo, shop):
        import services.store_dashboard as sd
        calls = []

        class Inline:
            def __init__(self, target, **kw):
                self.target = target

            def start(self):
                self.target()

        with patch.object(sd.threading, "Thread", Inline), \
                patch("services.geocoding.geocode_location",
                      side_effect=lambda c, st, co: calls.append((c, st)) or (40.0, -83.0)):
            StoreDashboard(repo).order_map([shop["summit"]], 30, now=NOW)
            m = StoreDashboard(repo).order_map([shop["summit"]], 30, now=NOW)
        assert calls == [("Columbus", "OH")]
        assert m["places"][0]["latitude"] == 40.0

    def test_monthly_rows(self, repo, shop):
        rows = StoreDashboard(repo).monthly_rows([shop["summit"]])
        october = next(r for r in rows if r["month"] == "2026-10")
        assert october["orders"] == 3 and october["refunds"] == 1
        assert october["sales"] == 4900 and october["refunded"] == 2800


# ── Routes ──────────────────────────────────────────────────


@pytest.fixture()
def store_repo(tmp_path):
    repo = StoreRepository(db_path=tmp_path / "store.db")
    with patch("routes.api.store._repo", return_value=repo):
        yield repo


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = user_id


class TestDashboardRoutes:
    def test_manager_sees_only_their_storefront(self, client, store_repo):
        explorer = store_repo.create_storefront("explorer", "Explorer Store")
        store_repo.add_storefront_admin(explorer, "mgr_1", "Mgr", "manager")
        summit_product = store_repo.create_product(sku="S", name="S", price_cents=100, stock_quantity=5)
        _sale(store_repo, summit_product, paid_days_ago=0)
        _login(client, "mgr_1")
        data = client.get("/api/store/admin/dashboard?days=30").get_json()
        assert data["totals"]["orders"] == 0
        data = client.get(f"/api/store/admin/dashboard?storefront_id={store_repo.default_storefront_id()}").get_json()
        assert data["totals"]["orders"] == 0
        assert client.get("/api/store/admin/dashboard?days=12").status_code == 400

    def test_fulfillment_cannot_see_sales(self, client, store_repo):
        explorer = store_repo.create_storefront("explorer", "Explorer Store")
        store_repo.add_storefront_admin(explorer, "ful_1", "Packer", "fulfillment")
        _login(client, "ful_1")
        assert client.get("/api/store/admin/dashboard").status_code == 403
        assert client.get("/api/store/admin/sales-summary.csv").status_code == 403

    def test_regular_user_refused(self, client, store_repo):
        _login(client, "nobody")
        assert client.get("/api/store/admin/dashboard").status_code == 403
        assert client.get("/api/store/admin/sales-summary.csv").status_code == 403

    def test_full_admin_csv(self, client, store_repo):
        product = store_repo.create_product(sku="S", name="S", price_cents=100, stock_quantity=5)
        _sale(store_repo, product, paid_days_ago=0)
        with patch("utils.store_auth.STORE_ADMIN_IDS", ["admin_1"]):
            _login(client, "admin_1")
            res = client.get("/api/store/admin/sales-summary.csv")
        assert res.status_code == 200
        lines = res.get_data(as_text=True).strip().splitlines()
        assert lines[0].startswith("month,storefront,orders")
        assert ",Summit Store,1,1,1.00,3.00,0.00,4.00,0,0.00,4.00" in lines[1]
