"""Tests for the custom order of store listings (drag to reorder in Store Admin)."""

import sqlite3

import pytest

from tests.test_storefronts import (  # noqa: F401  (fixtures)
    _make_shop, _product, full_admin, explorer_manager, explorer_fulfillment,
    store_repo,
)
from repositories.store import StoreRepository


@pytest.fixture()
def repo(tmp_path):
    return StoreRepository(db_path=tmp_path / "store.db")


def _skus(products):
    return [p["sku"] for p in products]


class TestRepository:
    def test_new_products_go_to_the_end(self, repo):
        _product(repo, "B", name="Zebra")
        _product(repo, "A", name="Apple")
        assert _skus(repo.list_products()) == ["B", "A"]

    def test_reorder_sets_public_order(self, repo):
        a, b, c = (_product(repo, s) for s in ("A", "B", "C"))
        repo.reorder_products(repo.default_storefront_id(), [c, a, b])
        assert _skus(repo.list_products()) == ["C", "A", "B"]

    def test_reorder_includes_hidden_products(self, repo):
        a, b = _product(repo, "A"), _product(repo, "B")
        repo.update_product(a, is_active=0)
        repo.reorder_products(repo.default_storefront_id(), [b, a])
        assert _skus(repo.list_products(include_inactive=True)) == ["B", "A"]
        assert _skus(repo.list_products()) == ["B"]

    def test_reorder_refuses_a_stale_list(self, repo):
        a, b = _product(repo, "A"), _product(repo, "B")
        sid = repo.default_storefront_id()
        for bad in ([a], [a, a], [a, b, 999]):
            with pytest.raises(ValueError):
                repo.reorder_products(sid, bad)
        assert _skus(repo.list_products()) == ["A", "B"]

    def test_storefronts_keep_their_own_order(self, repo):
        s = _make_shop(repo)
        exp2 = _product(repo, "EXP-2", storefront_id=s["explorer"])
        repo.reorder_products(s["explorer"], [exp2, s["explorer_product"]])
        assert _skus(repo.list_products()) == ["SUM-1", "EXP-2", "EXP-1"]

    def test_moving_storefront_puts_product_last(self, repo):
        s = _make_shop(repo)
        sum2 = _product(repo, "SUM-2")
        repo.reorder_products(s["summit"], [sum2, s["summit_product"]])
        repo.update_product(s["explorer_product"], storefront_id=s["summit"])
        assert _skus(repo.list_products()) == ["SUM-2", "SUM-1", "EXP-1"]

    def test_existing_products_keep_name_order_after_upgrade(self, tmp_path):
        db = tmp_path / "store.db"
        StoreRepository(db_path=db)
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE p2 AS SELECT * FROM products;
            DROP TABLE products;
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL, description TEXT DEFAULT '',
                price_cents INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
                image_url TEXT, stock_quantity INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1, max_per_user_monthly INTEGER,
                images TEXT, image_framing TEXT, storefront_id INTEGER,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            INSERT INTO products (sku, name, price_cents, storefront_id, created_at, updated_at)
                VALUES ('Z', 'Zebra', 1, 1, 'x', 'x'), ('A', 'Apple', 1, 1, 'x', 'x'),
                       ('M', 'Mango', 1, 1, 'x', 'x');
        """)
        conn.commit()
        conn.close()
        repo = StoreRepository(db_path=db)
        assert _skus(repo.list_products()) == ["A", "M", "Z"]
        # Opening it again doesn't reset a custom order
        rows = {p["sku"]: p["id"] for p in repo.list_products()}
        repo.reorder_products(1, [rows["Z"], rows["A"], rows["M"]])
        assert _skus(StoreRepository(db_path=db).list_products()) == ["Z", "A", "M"]


class TestReorderRoute:
    def test_full_admin_reorders(self, full_admin, store_repo):
        a, b = _product(store_repo, "A"), _product(store_repo, "B")
        resp = full_admin.post("/api/store/admin/products/reorder", json={
            "storefront_id": store_repo.default_storefront_id(), "product_ids": [b, a]})
        assert resp.status_code == 200
        products = full_admin.get("/api/store/products").get_json()["products"]
        assert _skus(products) == ["B", "A"]
        assert any(e["action"] == "reorder_products" for e in store_repo.list_audit())

    def test_stale_list_is_a_conflict(self, full_admin, store_repo):
        a = _product(store_repo, "A")
        _product(store_repo, "B")
        resp = full_admin.post("/api/store/admin/products/reorder", json={
            "storefront_id": store_repo.default_storefront_id(), "product_ids": [a]})
        assert resp.status_code == 409

    def test_bad_body(self, full_admin, store_repo):
        resp = full_admin.post("/api/store/admin/products/reorder",
                               json={"storefront_id": "x", "product_ids": [1]})
        assert resp.status_code == 400

    def test_manager_reorders_own_storefront_only(self, explorer_manager, store_repo):
        client, s = explorer_manager
        exp2 = _product(store_repo, "EXP-2", storefront_id=s["explorer"])
        resp = client.post("/api/store/admin/products/reorder", json={
            "storefront_id": s["explorer"], "product_ids": [exp2, s["explorer_product"]]})
        assert resp.status_code == 200
        resp = client.post("/api/store/admin/products/reorder", json={
            "storefront_id": s["summit"], "product_ids": [s["summit_product"]]})
        assert resp.status_code == 404

    def test_fulfillment_cannot_reorder(self, explorer_fulfillment):
        client, s = explorer_fulfillment
        resp = client.post("/api/store/admin/products/reorder", json={
            "storefront_id": s["explorer"], "product_ids": [s["explorer_product"]]})
        assert resp.status_code == 403
