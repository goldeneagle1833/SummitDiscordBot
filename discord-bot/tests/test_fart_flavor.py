"""Hardcoded fart flavor lines (no OpenAI)."""

import random
import sys
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault(
    "config",
    MagicMock(
        OPENAI_API_KEY="test",
        FART_CHANNEL_ID=1,
        GUILD_ID=1,
        LEADER_ROLE_ID=1,
    ),
)

from cogs.fart_flavor import (  # noqa: E402
    FART_FLAVOR_LINES,
    FARTLORD_PROCLAMATIONS,
    compose_fart_body,
    fart_roll_blurb,
    pick_fart_flavor,
    pick_fartlord_proclamation,
)
from cogs.fun import FunCog  # noqa: E402

TIERS = ("ordinary", "exceptional", "elite", "unique", "curio_shart")


class TestFlavorPools:
    def test_each_tier_has_twenty_unique_lines(self):
        for tier in TIERS:
            lines = FART_FLAVOR_LINES[tier]
            assert len(lines) == 20, f"{tier} should have 20 lines"
            assert len(set(lines)) == 20, f"{tier} lines must be unique"

    def test_every_line_includes_wind_emoji(self):
        for tier, lines in FART_FLAVOR_LINES.items():
            for line in lines:
                assert "💨" in line, f"{tier} missing 💨: {line!r}"

    def test_all_lines_globally_unique(self):
        all_lines = [line for lines in FART_FLAVOR_LINES.values() for line in lines]
        assert len(all_lines) == 100
        assert len(set(all_lines)) == 100


class TestPickAndBlurb:
    def test_pick_stays_in_tier_pool(self):
        rng = random.Random(0)
        for _ in range(30):
            line = rng.choice(FART_FLAVOR_LINES["elite"])
            assert line in FART_FLAVOR_LINES["elite"]
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("cogs.fart_flavor.random.choice", lambda seq: seq[0])
            assert pick_fart_flavor("unique") == FART_FLAVOR_LINES["unique"][0]
            assert pick_fart_flavor("unknown_tier") == FART_FLAVOR_LINES["ordinary"][0]

    def test_blurb_includes_title_and_flavor(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "cogs.fart_flavor.pick_fart_flavor",
                lambda fart_type: "💨 test flavor",
            )
            msg, typ = FunCog.classify_fart_roll(14)
            blurb = fart_roll_blurb(msg, typ)
            assert blurb.startswith("Ordinary Fart!")
            assert "💨 test flavor" in blurb

    def test_uber_rare_skips_default_curio_blurb(self):
        msg, typ = FunCog.classify_fart_roll(99)
        assert typ == "curio_shart"
        assert fart_roll_blurb(msg, typ, uber_variant="frostshart") == ""
        assert fart_roll_blurb(msg, typ, uber_variant=None).startswith("Curio Shart!")

    def test_compose_omits_curio_title_for_uber_rare(self):
        body = compose_fart_body(
            "❄ ***UBER-RARE CURIO: FROSTSHART***\n",
            "🧊 Frozen shoppers\n",
            "",
            "",
            "You earned 97 points.",
        )
        assert "Curio Shart" not in body
        assert "FROSTSHART" in body
        assert "You earned 97 points." in body

    def test_compose_keeps_default_curio_when_not_special(self):
        body = compose_fart_body(
            "",
            "",
            "",
            "Curio Shart! 💩💨💨💨💨 💩💨💨💨 A CURIO!",
            "You earned 98 points.",
        )
        assert body.startswith("Curio Shart!")
        assert "You earned 98 points." in body


class TestFartlordProclamations:
    def test_five_unique_proclamations_with_wind_emoji(self):
        assert len(FARTLORD_PROCLAMATIONS) == 5
        assert len(set(FARTLORD_PROCLAMATIONS)) == 5
        for line in FARTLORD_PROCLAMATIONS:
            assert "💨" in line

    def test_pick_returns_a_known_proclamation(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("cogs.fart_flavor.random.choice", lambda seq: seq[2])
            assert pick_fartlord_proclamation() == FARTLORD_PROCLAMATIONS[2]
