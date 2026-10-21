"""Season ticket roles: the active season's role decides who's a ticket holder,
and "current season ticket" store listings give the role on sale."""

import sqlite3
from unittest.mock import patch

import pytest

import webapp_config
from repositories.store import StoreRepository

ROLE_S8 = "111111111111111118"
ROLE_S9 = "111111111111111119"
BUYER = "222222222222222222"


@pytest.fixture()
def elo_db(tmp_path, monkeypatch):
    path = tmp_path / "elo.db"
    monkeypatch.setattr(webapp_config, "ELO_DB_PATH", path)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE season_ticket_roles (
               role_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
               event_id INTEGER, created_by TEXT, created_at TEXT NOT NULL,
               activated_at TEXT)"""
    )
    conn.commit()
    conn.close()

    def add(role_id, name, status, created_at="2026-10-01T00:00:00+00:00",
            activated_at=None):
        c = sqlite3.connect(path)
        c.execute("INSERT INTO season_ticket_roles (role_id, name, status, created_at, "
                  "activated_at) VALUES (?, ?, ?, ?, ?)",
                  (role_id, name, status, created_at, activated_at))
        c.commit()
        c.close()
    return add


class TestTicketHolderRoles:
    def test_falls_back_to_config_without_a_season_role(self, tmp_path, monkeypatch):
        from services.ticket_roles import ticket_holder_role_ids
        monkeypatch.setattr(webapp_config, "ELO_DB_PATH", tmp_path / "missing.db")
        monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", {"cfg"})
        assert ticket_holder_role_ids() == {"cfg"}

    def test_active_season_role_replaces_config(self, elo_db, monkeypatch):
        from services.ticket_roles import ticket_holder_role_ids
        monkeypatch.setattr(webapp_config, "TICKET_HOLDER_ROLE_IDS", {"cfg"})
        elo_db(ROLE_S8, "Season 8 Ticket", "active")
        elo_db(ROLE_S9, "Season 9 Ticket", "on_sale")
        # Next season's buyers don't count until it starts
        assert ticket_holder_role_ids() == {ROLE_S8}

    def test_selling_role_prefers_next_season(self, elo_db):
        from services.ticket_roles import selling_ticket_role, ticket_free_shipping_role_ids
        elo_db(ROLE_S8, "Season 8 Ticket", "active")
        assert selling_ticket_role()["role_id"] == ROLE_S8
        elo_db(ROLE_S9, "Season 9 Ticket", "on_sale")
        assert selling_ticket_role()["role_id"] == ROLE_S9
        assert ticket_free_shipping_role_ids() == {ROLE_S8, ROLE_S9}

    def test_roster_resyncs_after_new_season(self, elo_db):
        from services.ticket_holders import _synced_before_season_ticket
        elo_db(ROLE_S9, "Season 9 Ticket", "active",
               activated_at="2026-11-01T00:00:00+00:00")
        assert _synced_before_season_ticket("2026-10-20T10:00:00") is True
        assert _synced_before_season_ticket("2026-11-02T10:00:00") is False


class TestCurrentSeasonTicketListing:
    def _paid(self, repo, pid):
        order = repo.create_order(user_id=BUYER, username="Buyer",
                                  items=[{"product_id": pid, "quantity": 1}],
                                  shipping_address={})
        return repo.get_order(order["id"])

    def test_listing_accepts_current_season_ticket(self, tmp_path):
        repo = StoreRepository(db_path=tmp_path / "store.db")
        pid = repo.create_product(sku="T", name="Season Ticket", price_cents=1500,
                                  stock_quantity=5, product_type="discord_role",
                                  discord_role_id="season_ticket")
        assert repo.get_product(pid)["discord_role_id"] == "season_ticket"

    def test_gives_role_on_sale_and_refund_takes_back_that_one(self, tmp_path, elo_db):
        from services.store_roles import queue_role_grants, queue_role_removals
        repo = StoreRepository(db_path=tmp_path / "store.db")
        pid = repo.create_product(sku="T", name="Season Ticket", price_cents=1500,
                                  stock_quantity=5, product_type="discord_role",
                                  discord_role_id="season_ticket")
        elo_db(ROLE_S8, "Season 8 Ticket", "active")
        elo_db(ROLE_S9, "Season 9 Ticket", "on_sale")
        order = self._paid(repo, pid)
        assert queue_role_grants(repo, order) == 1
        assert [r["body"] for r in repo.fetch_pending_notifications(("discord_role_add",))] == [ROLE_S9]

        # Season 10 goes on sale later; the refund still removes Season 9
        conn = sqlite3.connect(webapp_config.ELO_DB_PATH)
        conn.execute("UPDATE season_ticket_roles SET status = 'past'")
        conn.commit()
        conn.close()
        elo_db("111111111111111110", "Season 10 Ticket", "on_sale")
        assert queue_role_removals(repo, repo.get_order(order["id"])) == 1
        assert [r["body"] for r in repo.fetch_pending_notifications(("discord_role_remove",))] == [ROLE_S9]

    def test_no_season_role_alerts_admins(self, tmp_path, elo_db):
        from services.store_roles import queue_role_grants
        repo = StoreRepository(db_path=tmp_path / "store.db")
        pid = repo.create_product(sku="T", name="Season Ticket", price_cents=1500,
                                  stock_quantity=5, product_type="discord_role",
                                  discord_role_id="season_ticket")
        assert queue_role_grants(repo, self._paid(repo, pid)) == 0
        alerts = repo.fetch_pending_notifications(("discord_admin",))
        assert len(alerts) == 1 and "!ticket_role" in alerts[0]["body"]

    def test_free_shipping_for_season_ticket_holders(self, elo_db):
        from services.store_checkout import free_shipping_role_ids
        elo_db(ROLE_S9, "Season 9 Ticket", "on_sale")
        with patch("services.store_checkout.FREE_SHIPPING_ROLE_IDS", {"patreon"}):
            assert free_shipping_role_ids() == {"patreon", ROLE_S9}
