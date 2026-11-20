"""Private (link only) store listings: off /store, sold through their own link + QR code."""

import pytest

from tests.test_storefronts import (  # noqa: F401  (fixtures)
    ADDRESS, _make_shop, _product, full_admin, explorer_manager, explorer_fulfillment,
    store_repo,
)
from repositories.store import StoreRepository


@pytest.fixture()
def repo(tmp_path):
    return StoreRepository(db_path=tmp_path / "store.db")


def _buy(repo, product_id, token=None, qty=1):
    item = {"product_id": product_id, "quantity": qty}
    if token is not None:
        item["private_token"] = token
    return repo.create_order(user_id="buyer_1", username="Buyer", items=[item],
                             shipping_address=ADDRESS)


class TestRepository:
    def test_private_listing_is_off_the_public_list(self, repo):
        a, b = _product(repo, "A"), _product(repo, "B")
        repo.set_private(b, True)
        assert [p["sku"] for p in repo.list_products()] == ["A"]
        assert len(repo.list_products(include_inactive=True)) == 2

    def test_private_link_finds_the_listing(self, repo):
        pid = _product(repo, "A")
        token = repo.set_private(pid, True)["private_token"]
        assert len(token) >= 16
        assert repo.get_private_product(token)["id"] == pid
        assert repo.get_private_product("nope") is None
        assert repo.get_private_product("") is None

    def test_link_stays_the_same_when_toggled(self, repo):
        pid = _product(repo, "A")
        token = repo.set_private(pid, True)["private_token"]
        repo.set_private(pid, False)
        # Public again: back on /store, and the link page no longer serves it
        assert [p["sku"] for p in repo.list_products()] == ["A"]
        assert repo.get_private_product(token) is None
        assert repo.set_private(pid, True)["private_token"] == token

    def test_new_link_retires_the_old_one(self, repo):
        pid = _product(repo, "A")
        old = repo.set_private(pid, True)["private_token"]
        new = repo.set_private(pid, True, new_link=True)["private_token"]
        assert new != old
        assert repo.get_private_product(old) is None
        assert repo.get_private_product(new)["id"] == pid

    def test_hidden_listing_or_storefront_closes_the_link(self, repo):
        s = _make_shop(repo)
        token = repo.set_private(s["explorer_product"], True)["private_token"]
        repo.update_product(s["explorer_product"], is_active=0)
        assert repo.get_private_product(token) is None
        repo.update_product(s["explorer_product"], is_active=1)
        repo.update_storefront(s["explorer"], is_active=0)
        assert repo.get_private_product(token) is None

    def test_buying_needs_the_link(self, repo):
        pid = _product(repo, "A")
        token = repo.set_private(pid, True)["private_token"]
        for bad in (None, "wrong"):
            with pytest.raises(ValueError, match="not available"):
                _buy(repo, pid, bad)
        assert repo.get_product(pid)["stock_quantity"] == 10
        order = _buy(repo, pid, token, qty=2)
        assert order["total_cents"] == 1000
        assert repo.get_product(pid)["stock_quantity"] == 8

    def test_public_listings_still_buy_without_a_token(self, repo):
        pid = _product(repo, "A")
        assert _buy(repo, pid)["total_cents"] == 500


class TestPublicRoutes:
    def test_catalog_leaves_private_out_and_hides_old_tokens(self, client, store_repo):
        a, b = _product(store_repo, "A"), _product(store_repo, "B")
        store_repo.set_private(a, True)
        store_repo.set_private(a, False)
        store_repo.set_private(b, True)
        products = client.get("/api/store/products").get_json()["products"]
        assert [p["sku"] for p in products] == ["A"]
        assert "private_token" not in products[0]

    def test_private_page_api(self, client, store_repo):
        pid = _product(store_repo, "A", max_per_user_monthly=3, ship_cards=6)
        token = store_repo.set_private(pid, True)["private_token"]
        data = client.get(f"/api/store/private/{token}").get_json()
        assert data["product"]["sku"] == "A"
        assert data["product"]["ship_cards"] == 6
        assert data["storefront"]["slug"] == "summit"
        assert "shipping_rules" in data
        assert client.get("/api/store/private/wrong").status_code == 404

    def test_new_content_skips_private_listings(self, store_repo, monkeypatch):
        from services import new_content
        monkeypatch.setattr("repositories.store.STORE_DB_PATH", store_repo.db_path)
        pid = _product(store_repo, "A", name="Secret Pack")
        store_repo.set_private(pid, True)
        assert new_content.latest_store_product() is None


class TestAdminRoutes:
    def test_toggle_private_and_get_link(self, full_admin, store_repo):
        pid = _product(store_repo, "TOK-1")
        res = full_admin.post(f"/api/store/admin/products/{pid}/private", json={"private": True})
        assert res.status_code == 200
        product = res.get_json()["product"]
        assert product["is_private"] == 1
        assert product["private_url"].endswith(f"/store/p/{product['private_token']}")
        listed = full_admin.get("/api/store/admin/products").get_json()["products"]
        assert listed[0]["private_url"] == product["private_url"]

    def test_new_link_endpoint(self, full_admin, store_repo):
        pid = _product(store_repo, "TOK-1")
        first = full_admin.post(f"/api/store/admin/products/{pid}/private",
                                json={"private": True}).get_json()["product"]
        second = full_admin.post(f"/api/store/admin/products/{pid}/private",
                                 json={"private": True, "new_link": True}).get_json()["product"]
        assert first["private_token"] != second["private_token"]

    def test_create_and_patch_with_is_private(self, full_admin, store_repo):
        res = full_admin.post("/api/store/admin/products", json={
            "sku": "P-1", "name": "Private", "price_cents": 999, "is_private": True})
        pid = res.get_json()["id"]
        assert store_repo.get_product(pid)["is_private"] == 1
        assert full_admin.patch(f"/api/store/admin/products/{pid}",
                                json={"is_private": False}).status_code == 200
        assert store_repo.get_product(pid)["is_private"] == 0
        # Other edits leave it alone
        full_admin.patch(f"/api/store/admin/products/{pid}", json={"is_private": True})
        full_admin.patch(f"/api/store/admin/products/{pid}", json={"name": "Renamed"})
        assert store_repo.get_product(pid)["is_private"] == 1

    def test_qr_png_and_sign(self, full_admin, store_repo):
        pid = _product(store_repo, "TOK-1")
        assert full_admin.get(f"/api/store/admin/products/{pid}/qr.png").status_code == 409
        full_admin.post(f"/api/store/admin/products/{pid}/private", json={"private": True})
        png = full_admin.get(f"/api/store/admin/products/{pid}/qr.png?download=1")
        assert png.status_code == 200
        assert png.data[:8] == b"\x89PNG\r\n\x1a\n"
        assert "attachment" in png.headers["Content-Disposition"]
        pdf = full_admin.get(f"/api/store/admin/products/{pid}/qr-sign.pdf")
        assert pdf.status_code == 200
        assert pdf.data[:4] == b"%PDF"

    def test_fulfillment_staff_cannot_toggle(self, explorer_fulfillment, store_repo):
        client, s = explorer_fulfillment
        res = client.post(f"/api/store/admin/products/{s['explorer_product']}/private",
                          json={"private": True})
        assert res.status_code == 403

    def test_manager_of_another_storefront_gets_404(self, explorer_manager, store_repo):
        client, s = explorer_manager
        res = client.post(f"/api/store/admin/products/{s['summit_product']}/private",
                          json={"private": True})
        assert res.status_code == 404
