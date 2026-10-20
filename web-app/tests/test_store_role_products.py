"""Discord role products (e.g. a season ticket) in the Summit Store."""

from unittest.mock import MagicMock, patch

import pytest

from repositories.store import StoreRepository

ROLE_ID = "123456789012345678"


def _repo(tmp_path) -> StoreRepository:
    return StoreRepository(db_path=tmp_path / "store.db")


def _ticket(repo, **overrides):
    fields = dict(sku="TICKET-S9", name="Season 9 Ticket", price_cents=1500,
                  stock_quantity=100, product_type="discord_role",
                  discord_role_id=ROLE_ID)
    fields.update(overrides)
    return repo.create_product(**fields)


def _order(repo, pid, user_id="111111111111111111", **overrides):
    fields = dict(user_id=user_id, username="Buyer",
                  items=[{"product_id": pid, "quantity": 1}],
                  shipping_address={})
    fields.update(overrides)
    return repo.create_order(**fields)


def _paid_event(repo, order, session_id="cs_role"):
    return {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id,
            "payment_status": "paid",
            "amount_total": repo.get_order(order["id"])["total_cents"],
            "currency": "usd",
            "metadata": {"order_id": str(order["id"])},
        }},
    }


class TestRoleProductRepository:
    def test_create_role_product(self, tmp_path):
        repo = _repo(tmp_path)
        product = repo.get_product(_ticket(repo))
        assert product["product_type"] == "discord_role"
        assert product["discord_role_id"] == ROLE_ID

    def test_products_default_to_physical(self, tmp_path):
        repo = _repo(tmp_path)
        pid = repo.create_product(sku="TOK", name="Token", price_cents=100,
                                  discord_role_id=ROLE_ID)
        product = repo.get_product(pid)
        assert product["product_type"] == "physical"
        assert product["discord_role_id"] is None

    def test_role_id_required(self, tmp_path):
        repo = _repo(tmp_path)
        with pytest.raises(ValueError, match="role ID"):
            _ticket(repo, discord_role_id="")
        with pytest.raises(ValueError, match="role ID"):
            _ticket(repo, discord_role_id="not-a-role")

    def test_summit_store_only(self, tmp_path):
        repo = _repo(tmp_path)
        other = repo.create_storefront("explorer", "Explorer")
        with pytest.raises(ValueError, match="Summit Store"):
            _ticket(repo, storefront_id=other)
        pid = _ticket(repo)
        with pytest.raises(ValueError, match="Summit Store"):
            repo.update_product(pid, storefront_id=other)

    def test_switch_back_to_physical_clears_role(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _ticket(repo)
        repo.update_product(pid, product_type="physical")
        product = repo.get_product(pid)
        assert product["product_type"] == "physical"
        assert product["discord_role_id"] is None

    def test_google_buyer_refused(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _ticket(repo)
        with pytest.raises(ValueError, match="Sign in with Discord"):
            _order(repo, pid, user_id="google_abc", auth_provider="google")
        assert repo.get_product(pid)["stock_quantity"] == 100

    def test_one_per_order(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _ticket(repo)
        with pytest.raises(ValueError, match="only buy one"):
            _order(repo, pid, items=[{"product_id": pid, "quantity": 2}])

    def test_order_is_digital(self, tmp_path):
        repo = _repo(tmp_path)
        ticket = _ticket(repo)
        token = repo.create_product(sku="TOK", name="Token", price_cents=100,
                                    stock_quantity=5)
        only_role = repo.get_order(_order(repo, ticket)["id"])
        mixed = repo.get_order(_order(repo, ticket, items=[
            {"product_id": ticket, "quantity": 1},
            {"product_id": token, "quantity": 1},
        ])["id"])
        assert repo.order_is_digital(only_role) is True
        assert repo.order_is_digital(mixed) is False


class TestRoleProductCheckout:
    def _service(self, repo):
        from services.store_checkout import StoreCheckoutService
        return StoreCheckoutService(repo=repo)

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.STRIPE_SHIPPING_RATE_DOMESTIC", "shr_domestic")
    def test_role_only_checkout_skips_shipping(self, mock_stripe, tmp_path):
        mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1", url="u")
        repo = _repo(tmp_path)
        pid = _ticket(repo)
        result = self._service(repo).create_checkout(
            user_id="111111111111111111", username="Buyer",
            items=[{"product_id": pid, "quantity": 1}],
        )
        params = mock_stripe.checkout.Session.create.call_args.kwargs
        assert "shipping_address_collection" not in params
        assert "shipping_options" not in params
        order = repo.get_order_by_number(result["order_number"])
        assert order["shipping_cents"] == 0
        assert order["total_cents"] == 1500

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.STRIPE_SHIPPING_RATE_DOMESTIC", "shr_domestic")
    def test_mixed_cart_still_ships(self, mock_stripe, tmp_path):
        mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1", url="u")
        repo = _repo(tmp_path)
        ticket = _ticket(repo)
        token = repo.create_product(sku="TOK", name="Token", price_cents=100,
                                    stock_quantity=5)
        self._service(repo).create_checkout(
            user_id="111111111111111111", username="Buyer",
            items=[{"product_id": ticket, "quantity": 1},
                   {"product_id": token, "quantity": 1}],
        )
        params = mock_stripe.checkout.Session.create.call_args.kwargs
        assert params["shipping_address_collection"] == {"allowed_countries": ["US"]}
        assert params["shipping_options"] == [{"shipping_rate": "shr_domestic"}]

    def test_paid_queues_role_and_delivers(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _ticket(repo)
        order = _order(repo, pid)
        repo.attach_payment(order["id"], "stripe", "cs_role")
        with patch("services.store_notifications.StoreNotificationService"):
            result = self._service(repo).handle_event(_paid_event(repo, order))
        assert result["handled"] is True
        assert repo.get_order(order["id"])["status"] == "delivered"
        rows = repo.fetch_pending_notifications(("discord_role_add",))
        assert len(rows) == 1
        assert rows[0]["recipient"] == "111111111111111111"
        assert rows[0]["body"] == ROLE_ID

    def test_duplicate_webhook_queues_role_once(self, tmp_path):
        repo = _repo(tmp_path)
        order = _order(repo, _ticket(repo))
        repo.attach_payment(order["id"], "stripe", "cs_role")
        svc = self._service(repo)
        with patch("services.store_notifications.StoreNotificationService"):
            svc.handle_event(_paid_event(repo, order))
            svc.handle_event(_paid_event(repo, order))
        assert len(repo.fetch_pending_notifications(("discord_role_add",))) == 1

    def test_physical_order_queues_no_role(self, tmp_path):
        repo = _repo(tmp_path)
        pid = repo.create_product(sku="TOK", name="Token", price_cents=100,
                                  stock_quantity=5)
        order = _order(repo, pid, shipping_cents=599)
        repo.attach_payment(order["id"], "stripe", "cs_tok")
        with patch("services.store_notifications.StoreNotificationService"):
            self._service(repo).handle_event(_paid_event(repo, order, "cs_tok"))
        assert repo.get_order(order["id"])["status"] == "paid"
        assert repo.fetch_pending_notifications(("discord_role_add",)) == []


@pytest.fixture()
def store_repo(tmp_path):
    repo = StoreRepository(db_path=tmp_path / "store.db")
    with patch("routes.api.store._repo", return_value=repo):
        yield repo


def _login(client, user_id, provider="discord", roles=None):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = "Someone"
        sess["auth_provider"] = provider
        sess["discord_roles"] = roles or []


class TestRoleProductRoutes:
    def _skus(self, client):
        return {p["sku"]: p for p in client.get("/api/store/products").get_json()["products"]}

    def test_hidden_unless_signed_in_with_discord(self, client, store_repo):
        _ticket(store_repo)
        store_repo.create_product(sku="TOK", name="Token", price_cents=100, stock_quantity=5)
        assert set(self._skus(client)) == {"TOK"}
        _login(client, "google_abc", provider="google")
        assert set(self._skus(client)) == {"TOK"}
        _login(client, "111111111111111111")
        assert set(self._skus(client)) == {"TOK", "TICKET-S9"}

    def test_has_role_flag(self, client, store_repo):
        _ticket(store_repo)
        _login(client, "111111111111111111", roles=[ROLE_ID])
        assert self._skus(client)["TICKET-S9"]["has_role"] is True
        _login(client, "111111111111111111", roles=["999"])
        assert self._skus(client)["TICKET-S9"]["has_role"] is False

    def test_full_admin_creates_role_product(self, client, store_repo):
        with patch("utils.store_auth.STORE_ADMIN_IDS", ["store_admin_1"]):
            _login(client, "store_admin_1")
            resp = client.post("/api/store/admin/products", json={
                "sku": "TICKET-S9", "name": "Season 9 Ticket", "price_cents": 1500,
                "stock_quantity": 50, "product_type": "discord_role",
                "discord_role_id": ROLE_ID,
            })
        assert resp.status_code == 201
        product = store_repo.get_product(resp.get_json()["id"])
        assert product["discord_role_id"] == ROLE_ID

    def test_storefront_manager_cannot_set_role(self, client, store_repo):
        summit = store_repo.default_storefront_id()
        store_repo.add_storefront_admin(summit, "mgr_1", "Mgr", "manager", "admin")
        token = store_repo.create_product(sku="TOK", name="Token", price_cents=100)
        _login(client, "mgr_1")
        resp = client.post("/api/store/admin/products", json={
            "sku": "T2", "name": "Ticket", "price_cents": 1500,
            "product_type": "discord_role", "discord_role_id": ROLE_ID,
        })
        assert resp.status_code == 403
        resp = client.patch(f"/api/store/admin/products/{token}", json={
            "product_type": "discord_role", "discord_role_id": ROLE_ID,
        })
        assert resp.status_code == 403
        # Ordinary edits still work, even when the form sends an empty role id
        resp = client.patch(f"/api/store/admin/products/{token}", json={
            "name": "Token v2", "product_type": "physical", "discord_role_id": None,
        })
        assert resp.status_code == 200

    def test_refund_queues_role_removal(self, client, store_repo):
        order = _order(store_repo, _ticket(store_repo))
        store_repo.mark_paid(order["id"])
        store_repo.set_status(order["id"], "delivered")
        with patch("utils.store_auth.STORE_ADMIN_IDS", ["store_admin_1"]), \
                patch("services.store_notifications.StoreNotificationService"):
            _login(client, "store_admin_1")
            resp = client.post(f"/api/store/admin/orders/{order['id']}/status",
                               json={"status": "refunded"})
        assert resp.status_code == 200
        rows = store_repo.fetch_pending_notifications(("discord_role_remove",))
        assert [r["body"] for r in rows] == [ROLE_ID]


class TestBundleProducts:
    def _service(self, repo):
        from services.store_checkout import StoreCheckoutService
        return StoreCheckoutService(repo=repo)

    def test_bundle_needs_role_and_summit(self, tmp_path):
        repo = _repo(tmp_path)
        with pytest.raises(ValueError, match="role ID"):
            _ticket(repo, product_type="bundle", discord_role_id="")
        other = repo.create_storefront("explorer", "Explorer")
        with pytest.raises(ValueError, match="Summit Store"):
            _ticket(repo, product_type="bundle", storefront_id=other)

    def test_bundle_is_discord_only(self, tmp_path):
        repo = _repo(tmp_path)
        pid = _ticket(repo, product_type="bundle")
        with pytest.raises(ValueError, match="Sign in with Discord"):
            _order(repo, pid, user_id="google_abc", auth_provider="google")

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.STRIPE_SHIPPING_RATE_DOMESTIC", "shr_domestic")
    def test_bundle_checkout_ships(self, mock_stripe, tmp_path):
        mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1", url="u")
        repo = _repo(tmp_path)
        pid = _ticket(repo, product_type="bundle")
        self._service(repo).create_checkout(
            user_id="111111111111111111", username="Buyer",
            items=[{"product_id": pid, "quantity": 1}],
        )
        params = mock_stripe.checkout.Session.create.call_args.kwargs
        assert params["shipping_address_collection"] == {"allowed_countries": ["US"]}
        assert params["shipping_options"] == [{"shipping_rate": "shr_domestic"}]

    def test_paid_bundle_gives_role_and_waits_to_ship(self, tmp_path):
        repo = _repo(tmp_path)
        order = _order(repo, _ticket(repo, product_type="bundle"), shipping_cents=599)
        repo.attach_payment(order["id"], "stripe", "cs_role")
        with patch("services.store_notifications.StoreNotificationService"):
            self._service(repo).handle_event(_paid_event(repo, order))
        assert repo.get_order(order["id"])["status"] == "paid"
        rows = repo.fetch_pending_notifications(("discord_role_add",))
        assert [r["body"] for r in rows] == [ROLE_ID]

    def test_receipt_mentions_role_and_tracking(self, tmp_path):
        from services.store_notifications import _receipt_next_step
        repo = _repo(tmp_path)
        order = repo.get_order(_order(repo, _ticket(repo, product_type="bundle"))["id"])
        text = _receipt_next_step(order)
        assert "Discord role" in text and "tracking" in text
