"""Store Admin: spot orders from the same buyer and pair them to ship together."""

from unittest.mock import patch

import pytest

from repositories.store import StoreRepository
from tests.test_store import _seed_order, _seed_product, store_admin_session, store_repo  # noqa: F401


def _paid(repo, pid, **kw):
    o = _seed_order(repo, product_id=pid, **kw)
    repo.mark_paid(o["id"])
    return o


ELSEWHERE = {"name": "Other", "line1": "9 Elm Rd", "city": "Dayton",
             "state": "OH", "postal": "45402", "country": "US"}


class TestGroupByBuyer:
    def _orders(self, repo):
        return {o["id"]: o for o in StoreRepository.group_orders_by_buyer(
            repo.list_orders_filtered())}

    def test_same_account_grouped(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a = _paid(repo, pid, user_id="u1")
        b = _paid(repo, pid, user_id="u1", shipping_address=ELSEWHERE)
        c = _paid(repo, pid, user_id="u2", shipping_address=ELSEWHERE | {"line1": "1 Oak"})
        orders = self._orders(repo)
        assert orders[a["id"]]["buyer_group"] == orders[b["id"]]["buyer_group"] is not None
        assert orders[a["id"]]["buyer_match"] == ["account"]
        assert orders[c["id"]]["buyer_group"] is None

    def test_same_address_different_account(self, tmp_path):
        """A buyer who checked out once with Discord and once with Google."""
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a = _paid(repo, pid, user_id="u1")
        b = _paid(repo, pid, user_id="g1", shipping_address={
            "name": "T", "line1": "123 MAIN ST.", "city": "Columbus",
            "state": "OH", "postal": "43201-1234", "country": "US"})
        orders = self._orders(repo)
        assert orders[a["id"]]["buyer_group"] == orders[b["id"]]["buyer_group"] is not None
        assert "address" in orders[a["id"]]["buyer_match"]

    def test_matches_chain(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a = _paid(repo, pid, user_id="u1")                              # home address
        b = _paid(repo, pid, user_id="u1", shipping_address=ELSEWHERE)  # same account
        c = _paid(repo, pid, user_id="u9", shipping_address=ELSEWHERE)  # same address as b
        orders = self._orders(repo)
        assert len({orders[x["id"]]["buyer_group"] for x in (a, b, c)}) == 1

    def test_other_storefront_not_grouped(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a = _paid(repo, pid, user_id="u1")
        b = _paid(repo, pid, user_id="u1")
        other = repo.create_storefront("other", "Other Store")
        with repo._connect() as conn:
            conn.execute("UPDATE orders SET storefront_id = ? WHERE id = ?", (other, b["id"]))
        orders = self._orders(repo)
        assert orders[a["id"]]["buyer_group"] is None
        assert orders[b["id"]]["buyer_group"] is None


class TestPairRepo:
    def test_pair_and_unpair(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a, b, c = (_paid(repo, pid) for _ in range(3))
        group = repo.pair_orders([a["id"], b["id"]])
        assert repo.get_order(a["id"])["ship_group"] == group
        # Adding a third order joins the same group
        assert repo.pair_orders([b["id"], c["id"]]) == group
        assert len(repo.orders_in_ship_group(group)) == 3
        repo.unpair_order(c["id"])
        assert repo.get_order(c["id"])["ship_group"] is None
        # Leaving one order alone clears the group
        repo.unpair_order(b["id"])
        assert repo.get_order(a["id"])["ship_group"] is None

    def test_only_paid_orders(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "s.db")
        pid = _seed_product(repo, stock_quantity=20)
        a = _paid(repo, pid)
        pending = _seed_order(repo, product_id=pid)
        with pytest.raises(ValueError):
            repo.pair_orders([a["id"], pending["id"]])
        with pytest.raises(ValueError):
            repo.pair_orders([a["id"]])


class TestShipTogetherRoutes:
    def test_list_has_buyer_group(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        _paid(store_repo, pid)
        _paid(store_repo, pid)
        orders = store_admin_session.get("/api/store/admin/orders").get_json()["orders"]
        assert {o["buyer_group"] for o in orders} != {None}

    def test_pair_then_ship_ships_both(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        a, b = _paid(store_repo, pid), _paid(store_repo, pid)
        r = store_admin_session.post("/api/store/admin/orders/pair",
                                     json={"order_ids": [a["id"], b["id"]]})
        assert r.status_code == 200
        with patch("services.store_notifications.StoreNotificationService") as n:
            r = store_admin_session.post(f"/api/store/admin/orders/{a['id']}/ship",
                                         json={"tracking_number": "T1", "tracking_carrier": "USPS"})
        assert r.status_code == 200
        assert sorted(r.get_json()["shipped_ids"]) == sorted([a["id"], b["id"]])
        for o in (a, b):
            got = store_repo.get_order(o["id"])
            assert got["status"] == "shipped" and got["tracking_number"] == "T1"
        assert n.return_value.notify_order_shipped.call_count == 2

    def test_paired_total_decides_tracking(self, store_admin_session, store_repo):
        """Two $30 orders in one package make a $60 package: tracking needed."""
        pid = _seed_product(store_repo, stock_quantity=20, price_cents=2401)
        a, b = _paid(store_repo, pid), _paid(store_repo, pid)
        store_repo.pair_orders([a["id"], b["id"]])
        r = store_admin_session.post(f"/api/store/admin/orders/{a['id']}/ship", json={})
        assert r.status_code == 400
        assert store_repo.get_order(b["id"])["status"] == "paid"

    def test_unpair_route(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        a, b = _paid(store_repo, pid), _paid(store_repo, pid)
        store_repo.pair_orders([a["id"], b["id"]])
        r = store_admin_session.post(f"/api/store/admin/orders/{a['id']}/unpair")
        assert r.status_code == 200
        assert store_repo.get_order(b["id"])["ship_group"] is None

    def test_pair_unpaid_refused(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        a = _paid(store_repo, pid)
        pending = _seed_order(store_repo, product_id=pid)
        r = store_admin_session.post("/api/store/admin/orders/pair",
                                     json={"order_ids": [a["id"], pending["id"]]})
        assert r.status_code == 409

    def test_refund_leaves_pair(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        a, b = _paid(store_repo, pid), _paid(store_repo, pid)
        store_repo.pair_orders([a["id"], b["id"]])
        with patch("services.store_notifications.StoreNotificationService"):
            r = store_admin_session.post(f"/api/store/admin/orders/{a['id']}/status",
                                         json={"status": "refunded"})
        assert r.status_code == 200
        assert store_repo.get_order(b["id"])["ship_group"] is None
