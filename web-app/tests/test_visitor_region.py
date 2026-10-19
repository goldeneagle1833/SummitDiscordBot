"""Visitor region for the Europe-only "Buy on Cardmarket" button."""


def test_european_country(client):
    resp = client.get("/api/visitor-region", headers={"CF-IPCountry": "de"})
    assert resp.get_json() == {"country": "DE", "europe": True}


def test_non_european_country(client):
    resp = client.get("/api/visitor-region", headers={"CF-IPCountry": "US"})
    assert resp.get_json() == {"country": "US", "europe": False}


def test_missing_or_unknown_country(client):
    assert client.get("/api/visitor-region").get_json() == {"country": None, "europe": None}
    for unknown in ("XX", "T1"):
        resp = client.get("/api/visitor-region", headers={"CF-IPCountry": unknown})
        assert resp.get_json() == {"country": None, "europe": None}
