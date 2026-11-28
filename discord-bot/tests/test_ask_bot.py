"""@mention questions + Discord feedback intake."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cogs import ask_bot
from services import ask_knowledge, feedback_intake


class TestKnowledge:
    def test_only_tracked_allowed_files_are_visible(self):
        files = ask_knowledge.visible_files()
        assert "discord-bot/services/provisional.py" in files
        assert not any(f.split("/")[-1] == "config.py" for f in files)
        assert not any(f.startswith(".github/") for f in files)
        assert not any(f.endswith(".db") or ".env" in f for f in files)

    def test_read_file_refuses_paths_outside_the_list(self):
        assert "isn't available" in ask_knowledge.read_file("../../etc/passwd")
        assert "isn't available" in ask_knowledge.read_file("discord-bot/config.py")
        assert "isn't available" in ask_knowledge.read_file(".github/workflows/deploy-bot.yml")

    def test_read_file_numbers_lines_and_caps_length(self):
        out = ask_knowledge.read_file("discord-bot/services/elo_service.py", 1, 5000)
        assert out.splitlines()[0].startswith("1: ")
        assert f"lines 1-{ask_knowledge.MAX_READ_LINES}" in out

    def test_search_finds_code(self):
        assert "provisional" in ask_knowledge.search_code("provisional", "discord-bot/services").lower()

    def test_secret_looking_lines_are_hidden(self):
        assert ask_knowledge._clean('API_KEY = "sk-ant-abcdefghijklmnop"') == "[line hidden]"
        assert ask_knowledge._clean("rating = 1500") == "rating = 1500"

    def test_pack_has_the_curated_files(self):
        pack = ask_knowledge.knowledge_pack()
        assert "===== discord-bot/services/provisional.py =====" in pack
        assert "===== web-app/frontend/src/pages/Help.jsx =====" in pack


class TestFeedbackHelpers:
    def test_guess_type(self):
        assert feedback_intake.guess_type("the button is broken") == "bug_report"
        assert feedback_intake.guess_type("idea: dark mode") == "feature_request"
        assert feedback_intake.guess_type("love the site") == "general"

    def test_make_title_cuts_long_first_line(self):
        title = feedback_intake.make_title("x" * 200 + "\nsecond line")
        assert len(title) == 90 and title.endswith("…")


def _message(content, *, mention=True, ref=None):
    bot_user = SimpleNamespace(id=999)
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 1
    msg.author.display_name = "Player"
    msg.guild = object()
    msg.id = 555
    msg.content = (f"<@{bot_user.id}> " if mention else "") + content
    msg.reference = ref
    msg.reply = AsyncMock(return_value=SimpleNamespace(id=777))
    msg.channel.id = 10
    typing = MagicMock()
    typing.__aenter__ = AsyncMock()
    typing.__aexit__ = AsyncMock(return_value=False)
    msg.channel.typing = MagicMock(return_value=typing)
    return msg, bot_user


def _cog(bot_user, client=None):
    bot = MagicMock()
    bot.user = bot_user
    bot.get_cog = MagicMock(return_value=None)
    cog = ask_bot.AskBotCog(bot)
    cog.client = client
    return cog


class TestAskBot:
    async def test_ignores_messages_without_a_mention(self):
        msg, me = _message("how does elo work", mention=False)
        cog = _cog(me, client=MagicMock())
        await cog.on_message(msg)
        msg.reply.assert_not_called()

    async def test_feedback_prefix_files_to_the_board(self, monkeypatch):
        submit = AsyncMock(return_value=12)
        monkeypatch.setattr(feedback_intake, "submit", submit)
        msg, me = _message("feedback: the LFG button does nothing on my phone")
        cog = _cog(me)
        await cog.on_message(msg)
        assert submit.await_args.kwargs["description"] == "the LFG button does nothing on my phone"
        assert submit.await_args.kwargs["feedback_type"] == "general"
        assert "feedback board" in msg.reply.await_args.args[0]

    async def test_question_is_answered_with_no_pings(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Ratings start at 1500. @everyone")],
        )
        client = MagicMock()
        client.beta.messages.create = AsyncMock(return_value=response)
        msg, me = _message("what rating do I start at?")
        cog = _cog(me, client=client)
        await cog.on_message(msg)
        kwargs = msg.reply.await_args.kwargs
        assert "1500" in msg.reply.await_args.args[0]
        assert kwargs["allowed_mentions"].everyone is False
        # Replying to the answer continues the conversation.
        assert 777 in cog._answers

    async def test_tool_round_trip(self, monkeypatch):
        tool_call = SimpleNamespace(
            stop_reason="tool_use",
            content=[SimpleNamespace(type="tool_use", id="t1", name="search_code",
                                     input={"query": "provisional", "path_contains": ""})],
        )
        final = SimpleNamespace(stop_reason="end_turn",
                                content=[SimpleNamespace(type="text", text="8 games.")])
        client = MagicMock()
        client.beta.messages.create = AsyncMock(side_effect=[tool_call, final])
        msg, me = _message("how many games until I'm not provisional?")
        cog = _cog(me, client=client)
        await cog.on_message(msg)
        second = client.beta.messages.create.await_args_list[1].kwargs["messages"]
        assert second[-1]["content"][0]["type"] == "tool_result"
        assert msg.reply.await_args.args[0] == "8 games."

    async def test_api_failure_gives_a_friendly_reply(self):
        client = MagicMock()
        client.beta.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        msg, me = _message("anything")
        cog = _cog(me, client=client)
        await cog.on_message(msg)
        assert "circuits" in msg.reply.await_args.args[0]

    async def test_per_user_limit(self):
        cog = _cog(SimpleNamespace(id=1))
        for _ in range(ask_bot.USER_LIMIT):
            assert cog._rate_limited(5) is None
        assert cog._rate_limited(5) is not None
        assert cog._rate_limited(6) is None

    async def test_no_key_says_so(self):
        msg, me = _message("how does pairing work?")
        cog = _cog(me, client=None)
        await cog.on_message(msg)
        assert "isn't set up" in msg.reply.await_args.args[0]

    async def test_answers_when_the_bots_role_is_tagged(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="After 8 games.")],
        )
        client = MagicMock()
        client.beta.messages.create = AsyncMock(return_value=response)
        msg, me = _message("", mention=False)
        msg.guild = SimpleNamespace(self_role=SimpleNamespace(id=4242))
        msg.content = "<@&4242> how does provisional rating work?"
        cog = _cog(me, client=client)
        await cog.on_message(msg)
        sent = client.beta.messages.create.await_args.kwargs["messages"][-1]["content"]
        assert sent == "how does provisional rating work?"
        assert msg.reply.await_args.args[0] == "After 8 games."

    async def test_other_role_tags_are_ignored(self):
        msg, me = _message("", mention=False)
        msg.guild = SimpleNamespace(self_role=SimpleNamespace(id=4242))
        msg.content = "<@&1111> hello mods"
        cog = _cog(me, client=MagicMock())
        await cog.on_message(msg)
        msg.reply.assert_not_called()
