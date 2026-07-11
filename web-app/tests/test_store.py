"""Tests for the store: repository, checkout service, and API routes."""

import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repositories.store import StoreRepository, ORDER_STATUSES


# ── Helpers ─────────────────────────────────────────────────


def _repo(tmp_path) -> StoreRepository:
    return StoreRepository(db_path=tmp_path / "store.db")


def _seed_product(repo, **overrides):
    defaults = dict(sku="TOKEN-001", name="Test Token", price_cents=999,
                    description="A test token", stock_quantity=10)
    defaults.update(overrides)
    return repo.create_product(**defaults)


def _seed_order(repo, product_id=None, user_id="user_1", **overrides):
    if product_id is None:
        product_id = _seed_product(repo)
    defaults = dict(
        user_id=user_id,
        username="TestUser",
        items=[{"product_id": product_id, "quantity": 1}],
        shipping_address={"name": "Test", "line1": "123 Main St",
                          "city": "Columbus", "state": "OH",
                          "postal": "43201", "country": "US"},
        shipping_cents=599,
    )
    defaults.update(overrides)
    return repo.create_order(**defaults)


# ══════════════════════════════════════════════════════════════
# Repository Tests
# ══════════════════════════════════════════════════════════════


class TestStoreRepositoryProducts:
    def test_create_and_get_product(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, sku="TOK-A", name="Alpha Token")
        product = repo.get_product(pid)
        assert product["sku"] == "TOK-A"
        assert product["name"] == "Alpha Token"
        assert product["price_cents"] == 999
        assert product["is_active"] == 1

    def test_list_products_excludes_inactive(self, tmp_path):
        repo = _repo(tmp_path)
        _seed_product(repo, sku="A")
        pid_b = _seed_product(repo, sku="B")
        repo.update_product(pid_b, is_active=0)

        active = repo.list_products(include_inactive=False)
        assert len(active) == 1
        assert active[0]["sku"] == "A"

        all_products = repo.list_products(include_inactive=True)
        assert len(all_products) == 2

    def test_update_product(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, name="Old Name", price_cents=100)
        repo.update_product(pid, name="New Name", price_cents=200)
        product = repo.get_product(pid)
        assert product["name"] == "New Name"
        assert product["price_cents"] == 200

    def test_update_product_ignores_invalid_fields(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        assert repo.update_product(pid, hacker_field="evil") is False

    def test_duplicate_sku_raises(self, tmp_path):
        repo = _repo(tmp_path)
        _seed_product(repo, sku="DUPE")
        with pytest.raises(sqlite3.IntegrityError):
            _seed_product(repo, sku="DUPE")

    def test_adjust_stock(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=5)
        assert repo.adjust_stock(pid, -3) is True
        assert repo.get_product(pid)["stock_quantity"] == 2
        # Cannot go below zero
        assert repo.adjust_stock(pid, -10) is False
        assert repo.get_product(pid)["stock_quantity"] == 2

    def test_get_nonexistent_product(self, tmp_path):
        repo = _repo(tmp_path)
        assert repo.get_product(9999) is None


class TestStoreRepositoryOrders:
    def test_create_order_reserves_stock(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=5)
        order = _seed_order(repo, product_id=pid,
                            items=[{"product_id": pid, "quantity": 3}])
        assert order["total_cents"] == 999 * 3 + 599  # subtotal + shipping
        product = repo.get_product(pid)
        assert product["stock_quantity"] == 2  # 5 - 3

    def test_create_order_insufficient_stock(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=1)
        with pytest.raises(ValueError, match="Insufficient stock"):
            _seed_order(repo, product_id=pid,
                        items=[{"product_id": pid, "quantity": 5}])

    def test_create_order_inactive_product(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        repo.update_product(pid, is_active=0)
        with pytest.raises(ValueError, match="not available"):
            _seed_order(repo, product_id=pid)

    def test_get_order_with_items(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, name="Cool Token")
        order_info = _seed_order(repo, product_id=pid)
        order = repo.get_order(order_info["id"])
        assert order["status"] == "pending_payment"
        assert len(order["items"]) == 1
        assert order["items"][0]["product_name"] == "Cool Token"

    def test_order_number_format(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        assert order["order_number"].startswith("SUM-")

    def test_mark_paid_idempotent(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        assert repo.mark_paid(order["id"]) is True
        # Second call: already paid, returns False
        assert repo.mark_paid(order["id"]) is False
        assert repo.get_order(order["id"])["status"] == "paid"

    def test_mark_shipped(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        repo.mark_paid(order["id"])
        assert repo.mark_shipped(order["id"], "TRACK123", "USPS") is True
        o = repo.get_order(order["id"])
        assert o["status"] == "shipped"
        assert o["tracking_number"] == "TRACK123"

    def test_mark_shipped_requires_paid(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        # Still pending_payment — ship should fail
        assert repo.mark_shipped(order["id"], "TRACK") is False

    def test_set_status_invalid(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        with pytest.raises(ValueError, match="Unknown status"):
            repo.set_status(order["id"], "bogus_status")

    def test_restock_order_items(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid,
                            items=[{"product_id": pid, "quantity": 4}])
        assert repo.get_product(pid)["stock_quantity"] == 6
        repo.restock_order_items(order["id"])
        assert repo.get_product(pid)["stock_quantity"] == 10

    def test_list_orders_by_user(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=20)
        _seed_order(repo, product_id=pid, user_id="alice")
        _seed_order(repo, product_id=pid, user_id="alice")
        _seed_order(repo, product_id=pid, user_id="bob")

        alice_orders = repo.list_orders_by_user("alice")
        assert len(alice_orders) == 2
        bob_orders = repo.list_orders_by_user("bob")
        assert len(bob_orders) == 1

    def test_list_orders_filter_by_status(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=20)
        o1 = _seed_order(repo, product_id=pid)
        o2 = _seed_order(repo, product_id=pid)
        repo.mark_paid(o1["id"])

        paid = repo.list_orders(status="paid")
        assert len(paid) == 1
        assert paid[0]["id"] == o1["id"]

    def test_attach_payment(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        assert repo.attach_payment(order["id"], "stripe", "cs_test_123")
        o = repo.get_order(order["id"])
        assert o["payment_provider"] == "stripe"
        assert o["payment_ref"] == "cs_test_123"

    def test_get_order_by_payment_ref(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo)
        order = _seed_order(repo, product_id=pid)
        repo.attach_payment(order["id"], "stripe", "cs_abc")
        found = repo.get_order_by_payment_ref("stripe", "cs_abc")
        assert found is not None
        assert found["id"] == order["id"]

    def test_last_shipping_address(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=20)
        _seed_order(repo, product_id=pid, user_id="u1",
                    shipping_address={"name": "Alice", "line1": "1 First St",
                                      "city": "A", "state": "OH",
                                      "postal": "11111"})
        addr = repo.last_shipping_address("u1")
        assert addr["name"] == "Alice"
        assert addr["line1"] == "1 First St"

    def test_update_shipping_address(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid, shipping_address={})
        assert repo.update_shipping_address(order["id"], {
            "name": "Jane Doe", "line1": "456 Oak Ave",
            "city": "Portland", "state": "OR", "postal": "97201",
        })
        o = repo.get_order(order["id"])
        assert o["ship_name"] == "Jane Doe"
        assert o["ship_city"] == "Portland"
        assert o["address_validated"] == 1


class TestStoreRepositoryAudit:
    def test_log_and_list_audit(self, tmp_path):
        repo = _repo(tmp_path)
        repo.log_action("admin1", "Admin", "test_action", "some details")
        audit = repo.list_audit()
        assert len(audit) == 1
        assert audit[0]["action"] == "test_action"


class TestStoreRepositoryNotifications:
    def test_enqueue_and_fetch(self, tmp_path):
        repo = _repo(tmp_path)
        nid = repo.enqueue_notification(None, "discord_dm", "12345",
                                        "Order Paid", "Your order is confirmed")
        pending = repo.fetch_pending_notifications(("discord_dm",))
        assert len(pending) == 1
        assert pending[0]["id"] == nid

    def test_mark_notification_sent(self, tmp_path):
        repo = _repo(tmp_path)
        nid = repo.enqueue_notification(None, "email", "a@b.com",
                                        "Shipped", "On its way")
        repo.mark_notification(nid, success=True)
        pending = repo.fetch_pending_notifications(("email",))
        assert len(pending) == 0

    def test_mark_notification_failed_retries(self, tmp_path):
        repo = _repo(tmp_path)
        nid = repo.enqueue_notification(None, "email", "a@b.com",
                                        "Test", "Body")
        repo.mark_notification(nid, success=False, error="timeout")
        # Still pending (1 attempt < 5 max)
        pending = repo.fetch_pending_notifications(("email",))
        assert len(pending) == 1
        assert pending[0]["last_error"] == "timeout"


# ══════════════════════════════════════════════════════════════
# Checkout Service Tests
# ══════════════════════════════════════════════════════════════


class TestStoreCheckoutService:
    def _service(self, repo):
        from services.store_checkout import StoreCheckoutService
        return StoreCheckoutService(repo=repo)

    @patch("services.store_checkout.STRIPE_SECRET_KEY", "")
    @patch("services.store_checkout.STRIPE_WEBHOOK_SECRET", "")
    def test_is_configured_false_when_empty(self, tmp_path):
        repo = _repo(tmp_path)
        svc = self._service(repo)
        assert svc.is_configured() is False

    @patch("services.store_checkout.STRIPE_SECRET_KEY", "sk_test_xxx")
    @patch("services.store_checkout.STRIPE_WEBHOOK_SECRET", "whsec_xxx")
    def test_is_configured_true(self, tmp_path):
        repo = _repo(tmp_path)
        svc = self._service(repo)
        assert svc.is_configured() is True

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.STRIPE_SECRET_KEY", "sk_test_xxx")
    @patch("services.store_checkout.STRIPE_WEBHOOK_SECRET", "whsec_xxx")
    def test_create_checkout_success(self, mock_stripe, tmp_path):
        mock_session = MagicMock()
        mock_session.id = "cs_test_session_123"
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_session_123"
        mock_stripe.checkout.Session.create.return_value = mock_session
        mock_stripe.StripeError = Exception

        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=5)
        svc = self._service(repo)

        result = svc.create_checkout(
            user_id="user_1", username="TestUser",
            items=[{"product_id": pid, "quantity": 2}],
            shipping_address={"name": "Test", "line1": "123 St",
                              "city": "C", "state": "OH", "postal": "43201"},
            email="test@example.com",
        )
        assert "order_number" in result
        assert result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_session_123"
        # Stock should be reserved
        assert repo.get_product(pid)["stock_quantity"] == 3

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.STRIPE_SECRET_KEY", "sk_test_xxx")
    @patch("services.store_checkout.STRIPE_WEBHOOK_SECRET", "whsec_xxx")
    def test_create_checkout_stripe_error_restocks(self, mock_stripe, tmp_path):
        mock_stripe.checkout.Session.create.side_effect = Exception("Stripe down")
        mock_stripe.StripeError = Exception

        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=5)
        svc = self._service(repo)

        with pytest.raises(Exception, match="Stripe down"):
            svc.create_checkout(
                user_id="u", username="U",
                items=[{"product_id": pid, "quantity": 2}],
                shipping_address={"name": "T", "line1": "1",
                                  "city": "C", "state": "S", "postal": "0"},
            )
        # Stock should be restored
        assert repo.get_product(pid)["stock_quantity"] == 5

    def test_handle_event_completed(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid)
        repo.attach_payment(order["id"], "stripe", "cs_test_abc")

        svc = self._service(repo)
        full_order = repo.get_order(order["id"])

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_abc",
                    "payment_status": "paid",
                    "amount_total": full_order["total_cents"],
                    "currency": "usd",
                    "metadata": {"order_id": str(order["id"]),
                                 "order_number": order["order_number"]},
                }
            },
        }
        with patch("services.store_notifications.StoreNotificationService"):
            result = svc.handle_event(event)
        assert result["handled"] is True
        assert repo.get_order(order["id"])["status"] == "paid"

    def test_handle_event_completed_saves_shipping(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid, shipping_address={})
        repo.attach_payment(order["id"], "stripe", "cs_test_ship")

        svc = self._service(repo)
        full_order = repo.get_order(order["id"])

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_ship",
                    "payment_status": "paid",
                    "amount_total": full_order["total_cents"],
                    "currency": "usd",
                    "metadata": {"order_id": str(order["id"])},
                    "shipping_details": {
                        "name": "Jane Doe",
                        "address": {
                            "line1": "456 Oak Ave",
                            "line2": "Apt 3",
                            "city": "Portland",
                            "state": "OR",
                            "postal_code": "97201",
                            "country": "US",
                        },
                    },
                }
            },
        }
        with patch("services.store_notifications.StoreNotificationService"):
            result = svc.handle_event(event)
        assert result["handled"] is True
        o = repo.get_order(order["id"])
        assert o["ship_name"] == "Jane Doe"
        assert o["ship_city"] == "Portland"
        assert o["ship_postal"] == "97201"

    def test_handle_event_amount_mismatch(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid)
        repo.attach_payment(order["id"], "stripe", "cs_test_mm")

        svc = self._service(repo)
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_mm",
                    "payment_status": "paid",
                    "amount_total": 1,  # wrong amount
                    "currency": "usd",
                    "metadata": {"order_id": str(order["id"])},
                }
            },
        }
        result = svc.handle_event(event)
        assert result["handled"] is False
        assert "mismatch" in result["reason"]
        # Order should NOT be marked paid
        assert repo.get_order(order["id"])["status"] == "pending_payment"

    def test_handle_event_expired(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _seed_product(repo, stock_quantity=10)
        order = _seed_order(repo, product_id=pid,
                            items=[{"product_id": pid, "quantity": 3}])
        repo.attach_payment(order["id"], "stripe", "cs_test_exp")

        assert repo.get_product(pid)["stock_quantity"] == 7  # 10 - 3

        svc = self._service(repo)
        event = {
            "type": "checkout.session.expired",
            "data": {
                "object": {
                    "id": "cs_test_exp",
                    "metadata": {"order_id": str(order["id"])},
                }
            },
        }
        result = svc.handle_event(event)
        assert result["handled"] is True
        assert repo.get_order(order["id"])["status"] == "cancelled"
        assert repo.get_product(pid)["stock_quantity"] == 10  # restocked

    def test_handle_event_unknown_type(self, tmp_path):
        repo = _repo(tmp_path)
        svc = self._service(repo)
        event = {"type": "some.other.event", "data": {"object": {}}}
        result = svc.handle_event(event)
        assert result["handled"] is False


# ══════════════════════════════════════════════════════════════
# API Route Tests
# ══════════════════════════════════════════════════════════════


@pytest.fixture()
def store_repo(tmp_path):
    """Provide a store repo with a temp DB and patch the route's _repo()."""
    repo = StoreRepository(db_path=tmp_path / "store.db")
    with patch("routes.api.store._repo", return_value=repo):
        yield repo


@pytest.fixture()
def store_admin_session(client, store_repo):
    """Client with store admin access."""
    with patch("utils.store_auth.STORE_ADMIN_IDS", ["store_admin_1"]):
        with client.session_transaction() as sess:
            sess["user_id"] = "store_admin_1"
            sess["username"] = "StoreAdmin"
        yield client


@pytest.fixture()
def buyer_session(client, store_repo):
    """Client with regular user session."""
    with client.session_transaction() as sess:
        sess["user_id"] = "buyer_1"
        sess["username"] = "Buyer"
    yield client


class TestStorePublicRoutes:
    def test_list_products_empty(self, client, store_repo):
        resp = client.get("/api/store/products")
        assert resp.status_code == 200
        assert resp.get_json()["products"] == []

    def test_list_products_excludes_inactive(self, client, store_repo):
        _seed_product(store_repo, sku="ACTIVE")
        pid = _seed_product(store_repo, sku="HIDDEN")
        store_repo.update_product(pid, is_active=0)
        resp = client.get("/api/store/products")
        products = resp.get_json()["products"]
        assert len(products) == 1
        assert products[0]["sku"] == "ACTIVE"


class TestStoreAdminRoutes:
    def test_admin_requires_auth(self, client, store_repo):
        with patch("utils.store_auth.is_store_admin", return_value=False):
            resp = client.get("/api/store/admin/products")
        assert resp.status_code == 403

    def test_admin_create_product(self, store_admin_session, store_repo):
        resp = store_admin_session.post("/api/store/admin/products",
                                        json={"sku": "NEW-1", "name": "New",
                                              "price_cents": 500})
        assert resp.status_code == 201
        assert "id" in resp.get_json()

    def test_admin_create_missing_fields(self, store_admin_session, store_repo):
        resp = store_admin_session.post("/api/store/admin/products",
                                        json={"sku": "X"})
        assert resp.status_code == 400

    def test_admin_update_product(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, sku="UPD-1")
        resp = store_admin_session.patch(f"/api/store/admin/products/{pid}",
                                          json={"name": "Updated"})
        assert resp.status_code == 200
        assert store_repo.get_product(pid)["name"] == "Updated"

    def test_admin_deactivate_product(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, sku="DEACT")
        resp = store_admin_session.post(f"/api/store/admin/products/{pid}/deactivate")
        assert resp.status_code == 200
        assert store_repo.get_product(pid)["is_active"] == 0

    def test_admin_list_orders(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        _seed_order(store_repo, product_id=pid)
        resp = store_admin_session.get("/api/store/admin/orders")
        assert resp.status_code == 200
        assert len(resp.get_json()["orders"]) == 1

    def test_admin_ship_order(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        order = _seed_order(store_repo, product_id=pid)
        store_repo.mark_paid(order["id"])

        with patch("services.store_notifications.StoreNotificationService"):
            resp = store_admin_session.post(
                f"/api/store/admin/orders/{order['id']}/ship",
                json={"tracking_number": "TRACK999", "tracking_carrier": "USPS"})
        assert resp.status_code == 200
        assert store_repo.get_order(order["id"])["status"] == "shipped"

    def test_admin_ship_requires_tracking(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        order = _seed_order(store_repo, product_id=pid)
        store_repo.mark_paid(order["id"])
        resp = store_admin_session.post(
            f"/api/store/admin/orders/{order['id']}/ship", json={})
        assert resp.status_code == 400

    def test_admin_cancel_restocks(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        order = _seed_order(store_repo, product_id=pid,
                            items=[{"product_id": pid, "quantity": 3}])
        assert store_repo.get_product(pid)["stock_quantity"] == 7

        resp = store_admin_session.post(
            f"/api/store/admin/orders/{order['id']}/status",
            json={"status": "cancelled"})
        assert resp.status_code == 200
        assert store_repo.get_product(pid)["stock_quantity"] == 10

    def test_admin_export_orders_csv(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        _seed_order(store_repo, product_id=pid)
        resp = store_admin_session.get("/api/store/admin/orders/export")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/csv")
        lines = resp.data.decode().strip().split("\n")
        assert len(lines) == 2  # header + 1 order
        assert "order_number" in lines[0]

    def test_admin_export_orders_filtered(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        o1 = _seed_order(store_repo, product_id=pid)
        _seed_order(store_repo, product_id=pid)
        store_repo.mark_paid(o1["id"])

        resp = store_admin_session.get("/api/store/admin/orders/export?status=paid")
        assert resp.status_code == 200
        lines = resp.data.decode().strip().split("\n")
        assert len(lines) == 2  # header + 1 paid order

    def test_admin_audit_log(self, store_admin_session, store_repo):
        store_repo.log_action("a", "A", "test", "detail")
        resp = store_admin_session.get("/api/store/admin/audit")
        assert resp.status_code == 200
        assert len(resp.get_json()["audit"]) == 1


class TestStoreBuyerRoutes:
    def test_checkout_no_auth(self, client, store_repo):
        resp = client.post("/api/store/checkout", json={"items": [{"product_id": 1, "quantity": 1}]})
        assert resp.status_code in (401, 403)

    def test_checkout_empty_cart(self, buyer_session, store_repo):
        resp = buyer_session.post("/api/store/checkout", json={"items": []})
        assert resp.status_code == 400

    def test_checkout_not_configured(self, buyer_session, store_repo):
        pid = _seed_product(store_repo)
        with patch("routes.api.store.StoreCheckoutService") as MockSvc:
            MockSvc.return_value.is_configured.return_value = False
            resp = buyer_session.post("/api/store/checkout", json={
                "items": [{"product_id": pid, "quantity": 1}],
            })
        assert resp.status_code == 503

    def test_my_orders_empty(self, buyer_session, store_repo):
        resp = buyer_session.get("/api/store/orders/mine")
        assert resp.status_code == 200
        assert resp.get_json()["orders"] == []

    def test_my_orders_only_own(self, buyer_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=20)
        _seed_order(store_repo, product_id=pid, user_id="buyer_1")
        _seed_order(store_repo, product_id=pid, user_id="other_user")

        resp = buyer_session.get("/api/store/orders/mine")
        orders = resp.get_json()["orders"]
        assert len(orders) == 1

    def test_my_orders_public_fields_only(self, buyer_session, store_repo):
        pid = _seed_product(store_repo, stock_quantity=10)
        _seed_order(store_repo, product_id=pid, user_id="buyer_1")

        resp = buyer_session.get("/api/store/orders/mine")
        order = resp.get_json()["orders"][0]
        # Should have public fields
        assert "order_number" in order
        assert "status" in order
        # Should NOT leak internal fields
        assert "user_id" not in order
        assert "ship_line1" not in order
        assert "payment_ref" not in order


class TestStoreWebhookRoute:
    def test_webhook_bad_signature(self, client, store_repo):
        with patch("routes.api.store.StoreCheckoutService") as MockSvc:
            MockSvc.return_value.is_configured.return_value = True
            MockSvc.return_value.construct_event.side_effect = Exception("bad sig")
            resp = client.post("/api/store/webhooks/stripe",
                               data=b"payload",
                               headers={"Stripe-Signature": "bad"})
        assert resp.status_code == 400

    def test_webhook_valid_event(self, client, store_repo):
        with patch("routes.api.store.StoreCheckoutService") as MockSvc:
            instance = MockSvc.return_value
            instance.is_configured.return_value = True
            instance.construct_event.return_value = {"type": "test"}
            instance.handle_event.return_value = {"handled": True}

            resp = client.post("/api/store/webhooks/stripe",
                               data=b"payload",
                               headers={"Stripe-Signature": "valid"})
        assert resp.status_code == 200
        assert resp.get_json()["handled"] is True
