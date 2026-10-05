"""Bracket pairing DMs."""

from unittest.mock import AsyncMock, MagicMock

import discord

from services.bracket_notify import (
    build_channel_embed,
    build_pairing_embed,
    find_top_cut_channel,
    post_pairings,
    send_pairing_dms,
)


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


def _batch(*round_titles, first_round=False):
    pairings = []
    for i, title in enumerate(round_titles):
        p = _payload()
        p["round_title"] = title
        p["first_round"] = first_round
        p["players"][0]["user_id"] = str(100 + i)
        pairings.append(p)
    return {
        "bracket_name": "Gothic Season 7 Postseason",
        "bracket_url": "https://sorcererssummit.com/brackets/gothic-s7",
        "pairings": pairings,
    }


async def test_a_batch_dms_every_player():
    user = MagicMock()
    user.send = AsyncMock()
    bot = MagicMock()
    bot.fetch_user = AsyncMock(return_value=user)

    results = await send_pairing_dms(bot, _batch("Round 1", "Round 1", "Round 1"))

    assert len(results) == 6 and all(r["sent"] for r in results)


def test_the_channel_post_lists_every_pairing():
    embed = build_channel_embed(_batch("Round 1", "Round 1", first_round=True))

    assert embed.title == "Gothic Season 7 Postseason: Round 1"
    assert "The bracket is live" in embed.description
    assert "<@100>" in embed.description and "<@101>" in embed.description
    assert embed.description.count("vs") == 2


def test_pairings_from_different_rounds_are_grouped():
    embed = build_channel_embed(_batch("Round 1", "Round 2"))

    assert "**Round 1**" in embed.description and "**Round 2**" in embed.description


def test_a_single_pairing_reads_as_one():
    embed = build_channel_embed(_payload())

    assert embed.title == "Gothic Season 7 Postseason: Semifinals"
    assert embed.description.startswith("New pairing:")


async def test_the_post_pings_the_players():
    channel = MagicMock()
    channel.send = AsyncMock()

    assert await post_pairings(MagicMock(), _payload(), channel) is True
    content = channel.send.await_args.kwargs["content"]
    assert "<@111>" in content and "<@222>" in content


async def test_no_channel_posts_nothing():
    assert await post_pairings(MagicMock(), _payload(), None) is False


def _guild_with(*names):
    channels = []
    for name in names:
        channel = MagicMock()
        channel.name = name
        channels.append(channel)
    guild = MagicMock()
    guild.text_channels = channels
    return guild, channels


def test_the_configured_channel_wins():
    configured = MagicMock()
    bot = MagicMock()
    bot.get_channel.return_value = configured

    assert find_top_cut_channel(bot, 1, 555) is configured
    bot.get_channel.assert_called_with(555)


def test_without_config_a_top_cut_named_channel_is_used():
    guild, channels = _guild_with("general", "🏆-top-cut", "lfg")
    bot = MagicMock()
    bot.get_guild.return_value = guild

    assert find_top_cut_channel(bot, 1, 0) is channels[1]


def test_no_matching_channel_is_none():
    guild, _ = _guild_with("general", "lfg")
    bot = MagicMock()
    bot.get_guild.return_value = guild

    assert find_top_cut_channel(bot, 1, None) is None
