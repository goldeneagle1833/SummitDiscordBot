"""Shipping per store listing: cards per item and a listing's own price."""

from unittest.mock import MagicMock, patch

import pytest

from repositories.store import StoreRepository
from services.store_shipping import cards_shipping_cents, listing_shipping_cents
from tests.test_store import (  # noqa: F401  (fixtures)
    _seed_product, store_repo, store_admin_session, buyer_session,
)


def _mock_stripe(mock_stripe):
    mock_stripe.checkout.Session.create.return_value = MagicMock(
        id="cs_1", url="https://pay/1")
    mock_stripe.StripeError = Exception


@pytest.fixture()
def repo(tmp_path):
    return StoreRepository(db_path=tmp_path / "store.db")


def _checkout(repo, lines, roles=None):
    from services.store_checkout import StoreCheckoutService
    StoreCheckoutService(repo).create_checkout(
        user_id="u", username="U",
        items=[{"product_id": pid, "quantity": qty} for pid, qty in lines],
        discord_roles=roles,
    )


class TestCardTiers:
    def test_up_to_six_cards_is_envelope(self):
        assert cards_shipping_cents(1) == 199
        assert cards_shipping_cents(6) == 199

    def test_over_six_is_ground_advantage(self):
        assert cards_shipping_cents(7) == 599
        assert cards_shipping_cents(40) == 599

    def test_no_cards_no_shipping(self):
        assert cards_shipping_cents(0) == 0

    def test_cards_add_up_across_the_cart(self):
        playset = {"ship_cards": 6, "shipping_cents": None}
        pack = {"ship_cards": 2, "shipping_cents": None}
        assert listing_shipping_cents([(playset, 1)]) == 199
        assert listing_shipping_cents([(pack, 3)]) == 199
        assert listing_shipping_cents([(playset, 1), (pack, 1)]) == 599
        assert listing_shipping_cents([(pack, 4)]) == 599

    def test_listing_price_wins_when_higher(self):
        mat = {"ship_cards": None, "shipping_cents": 899}
        pack = {"ship_cards": 2, "shipping_cents": None}
        assert listing_shipping_cents([(mat, 1), (pack, 1)]) == 899
        cheap = {"ship_cards": None, "shipping_cents": 100}
        assert listing_shipping_cents([(cheap, 1), (pack, 4)]) == 599

    def test_unset_listing_keeps_old_shipping(self):
        unset = {"ship_cards": None, "shipping_cents": None}
        pack = {"ship_cards": 2, "shipping_cents": None}
        assert listing_shipping_cents([(unset, 1), (pack, 1)]) is None
        assert listing_shipping_cents([]) is None


@patch("services.store_checkout.stripe")
@patch("services.store_checkout.STRIPE_SHIPPING_RATE_DOMESTIC", "shr_dom")
class TestCheckout:
    def _shipping_line(self, mock_stripe):
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        last = kwargs["line_items"][-1]["price_data"]
        return kwargs, (last["unit_amount"] if last["product_data"]["name"] == "Shipping" else None)

    def test_playset_ships_in_envelope(self, mock_stripe, repo):
        _mock_stripe(mock_stripe)
        playset = _seed_product(repo, sku="P", ship_cards=6)
        _checkout(repo, [(playset, 1)])
        kwargs, shipping = self._shipping_line(mock_stripe)
        assert shipping == 199
        assert "shipping_options" not in kwargs
        order = repo.list_orders()[0]
        assert order["shipping_cents"] == 199
        assert order["total_cents"] == 999 + 199

    def test_playset_and_pack_go_ground_advantage(self, mock_stripe, repo):
        _mock_stripe(mock_stripe)
        playset = _seed_product(repo, sku="P", ship_cards=6)
        pack = _seed_product(repo, sku="H", ship_cards=2)
        _checkout(repo, [(playset, 1), (pack, 1)])
        assert self._shipping_line(mock_stripe)[1] == 599

    def test_unset_listing_uses_stripe_rate_like_before(self, mock_stripe, repo):
        _mock_stripe(mock_stripe)
        pack = _seed_product(repo, sku="H", ship_cards=2)
        other = _seed_product(repo, sku="X")
        _checkout(repo, [(pack, 1), (other, 1)])
        kwargs, shipping = self._shipping_line(mock_stripe)
        assert kwargs["shipping_options"] == [{"shipping_rate": "shr_dom"}]
        assert shipping is None

    @patch("services.store_checkout.FREE_SHIPPING_ROLE_IDS", {"patreon"})
    def test_free_shipping_role_still_free(self, mock_stripe, repo):
        _mock_stripe(mock_stripe)
        pack = _seed_product(repo, sku="H", ship_cards=2)
        _checkout(repo, [(pack, 5)], roles=["patreon"])
        kwargs, shipping = self._shipping_line(mock_stripe)
        assert shipping is None
        assert repo.list_orders()[0]["shipping_cents"] == 0

    def test_resume_charges_listing_shipping_on_old_order(self, mock_stripe, repo):
        _mock_stripe(mock_stripe)
        pack = _seed_product(repo, sku="H")
        order = repo.create_order(
            user_id="u", username="U", items=[{"product_id": pack, "quantity": 1}],
            shipping_address={}, shipping_cents=0)
        repo.update_product(pack, ship_cards=2)
        from services.store_checkout import StoreCheckoutService
        StoreCheckoutService(repo).resume_checkout(repo.get_order(order["id"]))
        assert self._shipping_line(mock_stripe)[1] == 199
        fresh = repo.get_order(order["id"])
        assert fresh["shipping_cents"] == 199
        assert fresh["total_cents"] == 999 + 199


class TestAdminRoutes:
    def test_create_and_edit_listing_shipping(self, store_admin_session, store_repo):
        resp = store_admin_session.post("/api/store/admin/products", json={
            "sku": "PS", "name": "Playset", "price_cents": 1499,
            "ship_cards": 6, "shipping_cents": "",
        })
        assert resp.status_code == 201
        pid = resp.get_json()["id"]
        product = store_repo.get_product(pid)
        assert product["ship_cards"] == 6
        assert product["shipping_cents"] is None

        resp = store_admin_session.patch(f"/api/store/admin/products/{pid}",
                                         json={"shipping_cents": 350, "ship_cards": None})
        assert resp.status_code == 200
        product = store_repo.get_product(pid)
        assert (product["ship_cards"], product["shipping_cents"]) == (None, 350)

    def test_rejects_bad_values(self, store_admin_session, store_repo):
        pid = _seed_product(store_repo)
        for body in ({"ship_cards": -1}, {"ship_cards": "six"}, {"shipping_cents": 10_001}):
            resp = store_admin_session.patch(f"/api/store/admin/products/{pid}", json=body)
            assert resp.status_code == 400

    def test_catalog_lists_the_tiers(self, client, store_repo):
        data = client.get("/api/store/products").get_json()
        assert data["shipping_rules"] == {
            "envelope_max_cards": 6, "envelope_cents": 199, "ground_cents": 599,
        }
