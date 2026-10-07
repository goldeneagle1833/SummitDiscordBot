"""Tests for storefronts: per-storefront products, orders, admins and applications."""

import sqlite3
from unittest.mock import patch

import pytest

from repositories.store import StoreRepository, DEFAULT_STOREFRONT_SLUG, slugify


ADDRESS = {"name": "Test", "line1": "123 Main St", "city": "Columbus",
           "state": "OH", "postal": "43201", "country": "US"}


def _product(repo, sku, storefront_id=None, **overrides):
    fields = dict(sku=sku, name=f"Product {sku}", price_cents=500, stock_quantity=10,
                  storefront_id=storefront_id)
    fields.update(overrides)
    return repo.create_product(**fields)


def _order(repo, product_id, user_id="buyer_1"):
    return repo.create_order(
        user_id=user_id, username="Buyer",
        items=[{"product_id": product_id, "quantity": 1}],
        shipping_address=ADDRESS,
    )


@pytest.fixture()
def repo(tmp_path):
    return StoreRepository(db_path=tmp_path / "store.db")


@pytest.fixture()
def shop(repo):
    """Summit plus an Explorer storefront, one product and one order in each."""
    return _make_shop(repo)


# ── Repository ──────────────────────────────────────────────


class TestStorefrontRepository:
    def test_default_storefront_is_seeded_once(self, tmp_path):
        StoreRepository(db_path=tmp_path / "store.db")
        repo = StoreRepository(db_path=tmp_path / "store.db")
        storefronts = repo.list_storefronts()
        assert [s["slug"] for s in storefronts] == [DEFAULT_STOREFRONT_SLUG]

    def test_existing_rows_move_into_default_storefront(self, tmp_path):
        db = tmp_path / "store.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, description TEXT DEFAULT '',
                price_cents INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
                image_url TEXT, stock_quantity INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            INSERT INTO products (sku, name, price_cents, created_at, updated_at)
                VALUES ('OLD', 'Old product', 100, 'x', 'x');
        """)
        conn.commit()
        conn.close()

        repo = StoreRepository(db_path=db)
        product = repo.list_products()[0]
        assert product["storefront_id"] == repo.default_storefront_id()

    def test_new_product_defaults_to_summit(self, repo):
        pid = _product(repo, "A")
        assert repo.get_product(pid)["storefront_id"] == repo.default_storefront_id()

    def test_unknown_storefront_rejected(self, repo):
        with pytest.raises(ValueError):
            _product(repo, "A", storefront_id=999)

    def test_order_records_its_storefront(self, repo, shop):
        order = repo.get_order(shop["explorer_order"])
        assert order["storefront_id"] == shop["explorer"]

    def test_mixed_storefront_cart_is_rejected_without_taking_stock(self, repo, shop):
        with pytest.raises(ValueError, match="separately"):
            repo.create_order(
                user_id="buyer_1", username="Buyer",
                items=[{"product_id": shop["summit_product"], "quantity": 1},
                       {"product_id": shop["explorer_product"], "quantity": 1}],
                shipping_address=ADDRESS,
            )
        assert repo.get_product(shop["summit_product"])["stock_quantity"] == 9

    def test_hidden_storefront_hides_its_products(self, repo, shop):
        repo.update_storefront(shop["explorer"], is_active=0)
        skus = [p["sku"] for p in repo.list_products()]
        assert skus == ["SUM-1"]
        assert len(repo.list_products(include_inactive=True)) == 2

    def test_filter_orders_by_storefront(self, repo, shop):
        orders = repo.list_orders_filtered(storefront_ids=[shop["explorer"]])
        assert [o["id"] for o in orders] == [shop["explorer_order"]]
        assert orders[0]["storefront_name"] == "Explorer Store"
        assert repo.list_orders_filtered(storefront_ids=[]) == []

    def test_user_orders_carry_storefront_name(self, repo, shop):
        names = {o["storefront_name"] for o in repo.list_orders_by_user("buyer_1")}
        assert names == {"Summit Store", "Explorer Store"}

    def test_slug_rules(self, repo):
        with pytest.raises(ValueError):
            repo.create_storefront("Bad Slug", "Bad")
        with pytest.raises(ValueError, match="already"):
            repo.create_storefront(DEFAULT_STOREFRONT_SLUG, "Again")
        assert slugify("Explorer Store!") == "explorer-store"

    def test_admin_roles(self, repo, shop):
        repo.add_storefront_admin(shop["explorer"], "u1", "Helper", "fulfillment")
        repo.add_storefront_admin(shop["explorer"], "u1", "Helper", "manager")
        assert repo.storefront_roles_for_user("u1") == {shop["explorer"]: "manager"}
        with pytest.raises(ValueError):
            repo.add_storefront_admin(shop["explorer"], "u2", "X", "owner")
        assert repo.remove_storefront_admin(shop["explorer"], "u1")
        assert repo.storefront_roles_for_user("u1") == {}


class TestStorefrontApplicationsRepository:
    def _apply(self, repo, user_id="applicant", name="VIP"):
        return repo.create_storefront_application(
            user_id=user_id, username="Applicant", name=name,
            contact_email="a@example.com", description="Playmats",
            shipping="We ship from Ohio",
        )

    def test_one_pending_application_per_user(self, repo):
        self._apply(repo)
        with pytest.raises(ValueError):
            self._apply(repo)

    def test_approve_creates_storefront_and_manager(self, repo):
        app_id = self._apply(repo)
        storefront_id = repo.approve_storefront_application(app_id, "vip", "Bruce")
        assert repo.get_storefront(storefront_id)["name"] == "VIP"
        assert repo.storefront_roles_for_user("applicant") == {storefront_id: "manager"}
        assert repo.get_storefront_application(app_id)["status"] == "approved"
        with pytest.raises(ValueError):
            repo.approve_storefront_application(app_id, "vip-2", "Bruce")

    def test_approve_with_taken_slug_changes_nothing(self, repo):
        app_id = self._apply(repo)
        with pytest.raises(ValueError):
            repo.approve_storefront_application(app_id, DEFAULT_STOREFRONT_SLUG, "Bruce")
        assert repo.get_storefront_application(app_id)["status"] == "pending"
        assert repo.storefront_roles_for_user("applicant") == {}

    def test_decline(self, repo):
        app_id = self._apply(repo)
        assert repo.decline_storefront_application(app_id, "Bruce")
        assert not repo.decline_storefront_application(app_id, "Bruce")
        self._apply(repo)  # can apply again after a decline


# ── Routes ──────────────────────────────────────────────────


@pytest.fixture()
def store_repo(tmp_path):
    repo = StoreRepository(db_path=tmp_path / "store.db")
    with patch("routes.api.store._repo", return_value=repo):
        yield repo


def _login(client, user_id, username="User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username


@pytest.fixture()
def full_admin(client, store_repo):
    with patch("utils.store_auth.STORE_ADMIN_IDS", ["store_admin_1"]):
        _login(client, "store_admin_1", "Owner")
        yield client


def _make_shop(repo):
    explorer = repo.create_storefront("explorer", "Explorer Store")
    summit_product = _product(repo, "SUM-1")
    explorer_product = _product(repo, "EXP-1", storefront_id=explorer)
    return {
        "summit": repo.default_storefront_id(),
        "explorer": explorer,
        "summit_product": summit_product,
        "explorer_product": explorer_product,
        "summit_order": _order(repo, summit_product)["id"],
        "explorer_order": _order(repo, explorer_product)["id"],
    }


@pytest.fixture()
def explorer_manager(client, store_repo):
    s = _make_shop(store_repo)
    store_repo.add_storefront_admin(s["explorer"], "mgr_1", "Manager", "manager")
    _login(client, "mgr_1", "Manager")
    return client, s


@pytest.fixture()
def explorer_fulfillment(client, store_repo):
    s = _make_shop(store_repo)
    store_repo.add_storefront_admin(s["explorer"], "ful_1", "Packer", "fulfillment")
    _login(client, "ful_1", "Packer")
    return client, s


class TestPublicStorefrontRoutes:
    def test_list_storefronts(self, client, store_repo):
        _make_shop(store_repo)
        data = client.get("/api/store/storefronts").get_json()
        assert [s["slug"] for s in data["storefronts"]] == ["summit", "explorer"]
        assert "contact_email" not in data["storefronts"][0]

    def test_products_carry_storefront_id(self, client, store_repo):
        s = _make_shop(store_repo)
        products = client.get("/api/store/products").get_json()["products"]
        assert {p["sku"]: p["storefront_id"] for p in products} == {
            "SUM-1": s["summit"], "EXP-1": s["explorer"],
        }


class TestScopedAdminRoutes:
    def test_regular_user_is_refused(self, client, store_repo):
        _make_shop(store_repo)
        _login(client, "nobody")
        assert client.get("/api/store/admin/orders").status_code == 403

    def test_manager_sees_only_their_orders(self, explorer_manager):
        client, s = explorer_manager
        orders = client.get("/api/store/admin/orders").get_json()["orders"]
        assert [o["id"] for o in orders] == [s["explorer_order"]]

    def test_manager_cannot_open_other_storefront_order(self, explorer_manager):
        client, s = explorer_manager
        assert client.get(f"/api/store/admin/orders/{s['summit_order']}").status_code == 404
        resp = client.post(f"/api/store/admin/orders/{s['summit_order']}/status",
                           json={"status": "delivered"})
        assert resp.status_code == 404

    def test_manager_sees_only_their_products(self, explorer_manager):
        client, s = explorer_manager
        products = client.get("/api/store/admin/products").get_json()["products"]
        assert [p["sku"] for p in products] == ["EXP-1"]

    def test_manager_adds_product_to_own_storefront(self, explorer_manager, store_repo):
        client, s = explorer_manager
        resp = client.post("/api/store/admin/products", json={
            "sku": "EXP-2", "name": "Mat", "price_cents": 2000,
            "storefront_id": s["explorer"],
        })
        assert resp.status_code == 201
        assert store_repo.get_product(resp.get_json()["id"])["storefront_id"] == s["explorer"]

    def test_manager_cannot_add_to_other_storefront(self, explorer_manager):
        client, s = explorer_manager
        resp = client.post("/api/store/admin/products", json={
            "sku": "X", "name": "X", "price_cents": 1, "storefront_id": s["summit"],
        })
        assert resp.status_code == 403
        # Leaving storefront_id out means Summit, which is still not theirs
        resp = client.post("/api/store/admin/products",
                           json={"sku": "Y", "name": "Y", "price_cents": 1})
        assert resp.status_code == 403

    def test_manager_cannot_edit_other_storefront_product(self, explorer_manager):
        client, s = explorer_manager
        resp = client.patch(f"/api/store/admin/products/{s['summit_product']}",
                            json={"price_cents": 1})
        assert resp.status_code == 404

    def test_manager_cannot_move_product(self, explorer_manager):
        client, s = explorer_manager
        resp = client.patch(f"/api/store/admin/products/{s['explorer_product']}",
                            json={"storefront_id": s["summit"]})
        assert resp.status_code == 403

    def test_fulfillment_can_ship_but_not_edit_products(self, explorer_fulfillment, store_repo):
        client, s = explorer_fulfillment
        store_repo.mark_paid(s["explorer_order"])
        resp = client.post(f"/api/store/admin/orders/{s['explorer_order']}/ship",
                           json={"tracking_number": "T1"})
        assert resp.status_code == 200
        resp = client.patch(f"/api/store/admin/products/{s['explorer_product']}",
                            json={"price_cents": 1})
        assert resp.status_code == 403
        resp = client.post("/api/store/admin/products", json={
            "sku": "Z", "name": "Z", "price_cents": 1, "storefront_id": s["explorer"],
        })
        assert resp.status_code == 403

    def test_storefront_admin_cannot_download_backup_or_audit(self, explorer_manager):
        client, _ = explorer_manager
        assert client.get("/api/store/admin/backup").status_code == 403
        assert client.get("/api/store/admin/audit").status_code == 403

    def test_admin_me_for_manager(self, explorer_manager):
        client, s = explorer_manager
        data = client.get("/api/store/admin/me").get_json()
        assert data["is_full_admin"] is False
        assert [(x["id"], x["role"]) for x in data["storefronts"]] == [(s["explorer"], "manager")]

    def test_admin_me_for_full_admin(self, full_admin, store_repo):
        _make_shop(store_repo)
        data = full_admin.get("/api/store/admin/me").get_json()
        assert data["is_full_admin"] is True
        assert len(data["storefronts"]) == 2

    def test_full_admin_filters_orders_by_storefront(self, full_admin, store_repo):
        s = _make_shop(store_repo)
        orders = full_admin.get(
            f"/api/store/admin/orders?storefront_id={s['summit']}").get_json()["orders"]
        assert [o["id"] for o in orders] == [s["summit_order"]]


class TestStorefrontAdminManagement:
    def test_full_admin_adds_and_removes_admin(self, full_admin, store_repo):
        s = _make_shop(store_repo)
        url = f"/api/store/admin/storefronts/{s['explorer']}/admins"
        resp = full_admin.post(url, json={"user_id": "12345", "username": "Helper",
                                          "role": "fulfillment"})
        assert resp.status_code == 201
        admins = full_admin.get(url).get_json()["admins"]
        assert [(a["user_id"], a["role"]) for a in admins] == [("12345", "fulfillment")]
        assert full_admin.delete(f"{url}/12345").status_code == 200
        assert full_admin.delete(f"{url}/12345").status_code == 404

    def test_add_admin_validation(self, full_admin, store_repo):
        s = _make_shop(store_repo)
        url = f"/api/store/admin/storefronts/{s['explorer']}/admins"
        assert full_admin.post(url, json={"user_id": "abc"}).status_code == 400
        assert full_admin.post(url, json={"user_id": "1", "role": "owner"}).status_code == 400

    def test_manager_cannot_assign_admins(self, explorer_manager):
        client, s = explorer_manager
        resp = client.post(f"/api/store/admin/storefronts/{s['explorer']}/admins",
                           json={"user_id": "999", "role": "manager"})
        assert resp.status_code == 403

    def test_manager_can_see_own_team_only(self, explorer_manager):
        client, s = explorer_manager
        assert client.get(
            f"/api/store/admin/storefronts/{s['explorer']}/admins").status_code == 200
        assert client.get(
            f"/api/store/admin/storefronts/{s['summit']}/admins").status_code == 404

    def test_create_and_hide_storefront(self, full_admin, store_repo):
        resp = full_admin.post("/api/store/admin/storefronts", json={"name": "VIP Lounge"})
        assert resp.status_code == 201
        assert resp.get_json()["slug"] == "vip-lounge"
        sid = resp.get_json()["id"]
        assert full_admin.patch(f"/api/store/admin/storefronts/{sid}",
                                json={"is_active": False}).status_code == 200
        assert not store_repo.get_storefront(sid)["is_active"]

    def test_manager_cannot_create_storefront(self, explorer_manager):
        client, _ = explorer_manager
        resp = client.post("/api/store/admin/storefronts", json={"name": "Mine"})
        assert resp.status_code == 403


class TestStorefrontApplicationRoutes:
    BODY = {"name": "VIP", "contact_email": "vip@example.com",
            "description": "Supporter gear", "shipping": "Ohio", "agreed": True}

    def test_apply_requires_login(self, client, store_repo):
        resp = client.post("/api/store/storefront-applications", json=self.BODY)
        assert resp.status_code == 401

    def test_apply_and_list_mine(self, client, store_repo):
        _login(client, "555", "Applicant")
        assert client.post("/api/store/storefront-applications",
                           json=self.BODY).status_code == 201
        assert client.post("/api/store/storefront-applications",
                           json=self.BODY).status_code == 409
        mine = client.get("/api/store/storefront-applications/mine").get_json()
        assert [a["status"] for a in mine["applications"]] == ["pending"]

    def test_apply_needs_agreement_and_fields(self, client, store_repo):
        _login(client, "555")
        assert client.post("/api/store/storefront-applications",
                           json={**self.BODY, "agreed": False}).status_code == 400
        assert client.post("/api/store/storefront-applications",
                           json={**self.BODY, "shipping": ""}).status_code == 400

    def test_full_admin_approves(self, full_admin, store_repo):
        app_id = store_repo.create_storefront_application(
            user_id="555", username="Applicant", name="VIP",
            contact_email="vip@example.com", description="x", shipping="y")
        resp = full_admin.post(
            f"/api/store/admin/storefront-applications/{app_id}/approve", json={})
        assert resp.status_code == 200
        assert resp.get_json()["slug"] == "vip"
        sid = resp.get_json()["storefront_id"]
        assert store_repo.storefront_roles_for_user("555") == {sid: "manager"}

    def test_manager_cannot_review_applications(self, explorer_manager):
        client, _ = explorer_manager
        assert client.get("/api/store/admin/storefront-applications").status_code == 403


# ── Payments: each storefront's own Stripe account ──────────


from unittest.mock import MagicMock  # noqa: E402

from services.store_checkout import StoreCheckoutService  # noqa: E402


def _paid_event(order, session_id, account=None):
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id, "payment_status": "paid",
            "amount_total": order["total_cents"], "currency": "usd",
            "metadata": {"order_id": str(order["id"])},
        }},
    }
    if account:
        event["account"] = account
    return event


def _mock_session(mock_stripe):
    mock_stripe.StripeError = Exception
    mock_stripe.checkout.Session.create.return_value = MagicMock(id="cs_1", url="https://pay")


class TestStorefrontPayments:
    def test_summit_always_accepts_payments(self, repo, shop):
        summit = repo.get_storefront(shop["summit"])
        assert repo.accepts_payments(summit)
        assert repo.stripe_account_for(summit) is None

    def test_storefront_needs_a_ready_stripe_account(self, repo, shop):
        explorer = repo.get_storefront(shop["explorer"])
        assert not repo.accepts_payments(explorer)
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", False)
        assert not repo.accepts_payments(repo.get_storefront(shop["explorer"]))
        repo.set_stripe_charges_enabled("acct_exp", True)
        explorer = repo.get_storefront(shop["explorer"])
        assert repo.accepts_payments(explorer)
        assert repo.stripe_account_for(explorer) == "acct_exp"

    @patch("services.store_checkout.stripe")
    def test_checkout_refused_until_connected_without_taking_stock(self, mock_stripe, repo, shop):
        _mock_session(mock_stripe)
        with pytest.raises(ValueError, match="isn't taking orders yet"):
            StoreCheckoutService(repo).create_checkout(
                user_id="u", username="U",
                items=[{"product_id": shop["explorer_product"], "quantity": 1}],
            )
        assert repo.get_product(shop["explorer_product"])["stock_quantity"] == 9  # only the fixture order
        mock_stripe.checkout.Session.create.assert_not_called()

    @patch("services.store_checkout.stripe")
    @patch("services.store_checkout.FREE_SHIPPING_ROLE_IDS", {"patreon"})
    @patch("services.store_checkout.STRIPE_SHIPPING_RATE_DOMESTIC", "shr_dom")
    @patch("services.store_checkout.STRIPE_SHIPPING_RATE_INTERNATIONAL", "shr_int")
    def test_checkout_runs_on_the_storefront_account(self, mock_stripe, repo, shop):
        _mock_session(mock_stripe)
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", True)
        repo.update_storefront(shop["explorer"], shipping_cents=350)
        StoreCheckoutService(repo).create_checkout(
            user_id="u", username="U",
            items=[{"product_id": shop["explorer_product"], "quantity": 1}],
            discord_roles=["patreon"],
        )
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["stripe_account"] == "acct_exp"
        # Summit's shipping rates and free-shipping perk don't apply
        assert "shipping_options" not in kwargs
        assert kwargs["line_items"][-1]["price_data"]["unit_amount"] == 350

    @patch("services.store_checkout.stripe")
    def test_summit_checkout_stays_on_platform(self, mock_stripe, repo, shop):
        _mock_session(mock_stripe)
        StoreCheckoutService(repo).create_checkout(
            user_id="u", username="U",
            items=[{"product_id": shop["summit_product"], "quantity": 1}],
        )
        assert "stripe_account" not in mock_stripe.checkout.Session.create.call_args.kwargs

    def test_connected_payment_marks_its_order_paid(self, repo, shop):
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", True)
        order = repo.get_order(shop["explorer_order"])
        with patch("services.store_notifications.StoreNotificationService"):
            result = StoreCheckoutService(repo).handle_event(_paid_event(order, "cs_x", "acct_exp"))
        assert result["handled"] is True
        assert repo.get_order(order["id"])["status"] == "paid"

    def test_storefront_account_cannot_pay_another_storefronts_order(self, repo, shop):
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", True)
        order = repo.get_order(shop["summit_order"])
        result = StoreCheckoutService(repo).handle_event(_paid_event(order, "cs_x", "acct_exp"))
        assert result["handled"] is False
        assert repo.get_order(order["id"])["status"] == "pending_payment"

    def test_platform_event_cannot_pay_connected_order(self, repo, shop):
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", True)
        order = repo.get_order(shop["explorer_order"])
        result = StoreCheckoutService(repo).handle_event(_paid_event(order, "cs_x"))
        assert result["handled"] is False

    def test_account_updated_event_turns_on_payments(self, repo, shop):
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", False)
        StoreCheckoutService(repo).handle_event({
            "type": "account.updated",
            "data": {"object": {"id": "acct_exp", "charges_enabled": True}},
            "account": "acct_exp",
        })
        assert repo.accepts_payments(repo.get_storefront(shop["explorer"]))

    @patch("services.store_checkout.stripe")
    def test_cancel_expires_session_on_the_storefront_account(self, mock_stripe, repo, shop):
        mock_stripe.StripeError = Exception
        repo.set_storefront_stripe(shop["explorer"], "acct_exp", True)
        repo.attach_payment(shop["explorer_order"], "stripe", "cs_open")
        StoreCheckoutService(repo).cancel_order(repo.get_order(shop["explorer_order"]))
        mock_stripe.checkout.Session.expire.assert_called_once_with("cs_open", stripe_account="acct_exp")


class TestStorefrontPaymentRoutes:
    def test_public_list_says_who_takes_orders(self, client, store_repo):
        _make_shop(store_repo)
        data = client.get("/api/store/storefronts").get_json()["storefronts"]
        assert {s["slug"]: s["accepts_payments"] for s in data} == {"summit": True, "explorer": False}
        assert "stripe_account_id" not in data[0]

    @patch("services.store_checkout.STRIPE_SECRET_KEY", "sk")
    @patch("services.store_checkout.STRIPE_WEBHOOK_SECRET", "wh")
    @patch("services.store_checkout.stripe")
    def test_manager_starts_onboarding(self, mock_stripe, explorer_manager, store_repo):
        client, s = explorer_manager
        mock_stripe.Account.create.return_value = MagicMock(id="acct_new")
        mock_stripe.AccountLink.create.return_value = MagicMock(url="https://connect.stripe.com/x")
        res = client.post(f"/api/store/admin/storefronts/{s['explorer']}/stripe/onboard")
        assert res.status_code == 200
        assert res.get_json()["url"] == "https://connect.stripe.com/x"
        assert store_repo.get_storefront(s["explorer"])["stripe_account_id"] == "acct_new"

        # A second visit resumes onboarding on the same account
        client.post(f"/api/store/admin/storefronts/{s['explorer']}/stripe/onboard")
        assert mock_stripe.Account.create.call_count == 1

    def test_manager_cannot_onboard_other_storefront(self, explorer_manager):
        client, s = explorer_manager
        res = client.post(f"/api/store/admin/storefronts/{s['summit']}/stripe/onboard")
        assert res.status_code == 404

    def test_fulfillment_cannot_onboard(self, explorer_fulfillment):
        client, s = explorer_fulfillment
        res = client.post(f"/api/store/admin/storefronts/{s['explorer']}/stripe/onboard")
        assert res.status_code == 404

    def test_summit_cannot_be_onboarded(self, full_admin, store_repo):
        sid = store_repo.default_storefront_id()
        res = full_admin.post(f"/api/store/admin/storefronts/{sid}/stripe/onboard")
        assert res.status_code == 400

    @patch("services.store_checkout.stripe")
    def test_status_refresh(self, mock_stripe, explorer_manager, store_repo):
        client, s = explorer_manager
        store_repo.set_storefront_stripe(s["explorer"], "acct_exp", False)
        mock_stripe.Account.retrieve.return_value = {"charges_enabled": True}
        data = client.get(f"/api/store/admin/storefronts/{s['explorer']}/stripe?refresh=1").get_json()
        assert data["accepts_payments"] is True

    def test_only_full_admin_disconnects(self, explorer_manager, store_repo):
        client, s = explorer_manager
        store_repo.set_storefront_stripe(s["explorer"], "acct_exp", True)
        res = client.delete(f"/api/store/admin/storefronts/{s['explorer']}/stripe")
        assert res.status_code == 403

    def test_full_admin_sets_shipping(self, full_admin, store_repo):
        s = _make_shop(store_repo)
        res = full_admin.patch(f"/api/store/admin/storefronts/{s['explorer']}", json={"shipping_cents": 450})
        assert res.status_code == 200
        assert store_repo.get_storefront(s["explorer"])["shipping_cents"] == 450
        res = full_admin.patch(f"/api/store/admin/storefronts/{s['explorer']}", json={"shipping_cents": -1})
        assert res.status_code == 400
