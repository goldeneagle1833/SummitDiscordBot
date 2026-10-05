"""Bracket pairing DMs."""

from unittest.mock import AsyncMock, MagicMock

import discord

from services.bracket_notify import build_pairing_embed, send_pairing_dms


def _payload():
    one = {"user_id": "111", "name": "Alice", "seed": 1, "deck_submitted": True}
    two = {"user_id": "222", "name": "Bob", "seed": 4, "deck_submitted": False}
    return {
        "bracket_name": "Gothic Season 7 Postseason",
        "round_title": "Semifinals",
        "match_no": 5,
        "bracket_url": "https://sorcererssummit.com/brackets/gothic-s7",
        "players": [{**one, "opponent": two}, {**two, "opponent": one}],
    }


def _text(embed):
    return " ".join(
        [embed.title or "", embed.description or ""]
        + [f"{f.name} {f.value}" for f in embed.fields]
    )


def test_the_message_names_the_round_opponent_and_link():
    payload = _payload()
    text = _text(build_pairing_embed(payload, payload["players"][0]))

    assert "Gothic Season 7 Postseason: Semifinals" in text
    assert "<@222>" in text and "Bob" in text
    assert "seed 4" in text
    assert payload["bracket_url"] in text


def test_only_a_player_without_a_deck_is_asked_for_one():
    payload = _payload()
    with_deck = _text(build_pairing_embed(payload, payload["players"][0]))
    without_deck = _text(build_pairing_embed(payload, payload["players"][1]))

    assert "Submit your decklist" not in with_deck
    assert "Submit your decklist" in without_deck


async def test_both_players_are_dmed():
    user = MagicMock()
    user.send = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=user)

    results = await send_pairing_dms(bot, _payload())

    assert [r["sent"] for r in results] == [True, True]
    assert user.send.await_count == 2


async def test_a_closed_dm_or_google_player_does_not_stop_the_other():
    payload = _payload()
    payload["players"][1]["user_id"] = "google_abc"
    user = MagicMock()
    user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), "closed"))
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=user)

    results = await send_pairing_dms(bot, payload)

    assert results[0]["reason"] == "dms_disabled"
    assert results[1]["reason"] == "not_discord_id"


def test_round_one_and_later_rounds_read_differently():
    payload = _payload()
    later = build_pairing_embed(payload, payload["players"][0]).description
    payload["first_round"] = True
    first = build_pairing_embed(payload, payload["players"][0]).description

    assert "You advanced" in later
    assert "first-round match" in first and "You advanced" not in first
