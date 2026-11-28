"""@mention feedback (no AI) + Discord feedback helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from cogs import mention_feedback
from services import feedback_intake


def _message(content, *, mention=True):
    msg = MagicMock()
    msg.author.bot = False
    msg.author.id = 1
    msg.author.display_name = "Player"
    msg.guild = object()
    msg.id = 555
    msg.content = ("<@999> " if mention else "") + content
    msg.reply = AsyncMock()
    return msg


def _cog():
    bot = MagicMock()
    bot.user = SimpleNamespace(id=999)
    bot.get_cog = MagicMock(return_value=None)
    return mention_feedback.MentionFeedbackCog(bot)


class TestMentionFeedback:
    async def test_feedback_is_filed(self, monkeypatch):
        submit = AsyncMock(return_value=12)
        monkeypatch.setattr(feedback_intake, "submit", submit)
        msg = _message("feedback: the LFG button does nothing on my phone")
        await _cog().on_message(msg)
        assert submit.await_args.kwargs["description"] == "the LFG button does nothing on my phone"
        assert "feedback board" in msg.reply.await_args.args[0]

    async def test_role_tag_counts(self, monkeypatch):
        submit = AsyncMock(return_value=3)
        monkeypatch.setattr(feedback_intake, "submit", submit)
        msg = _message("", mention=False)
        msg.guild = SimpleNamespace(self_role=SimpleNamespace(id=4242))
        msg.content = "<@&4242> bug: leaderboard shows the wrong season"
        await _cog().on_message(msg)
        assert submit.await_args.kwargs["feedback_type"] == "bug_report"

    async def test_questions_get_no_reply(self, monkeypatch):
        submit = AsyncMock()
        monkeypatch.setattr(feedback_intake, "submit", submit)
        msg = _message("how does provisional rating work?")
        await _cog().on_message(msg)
        msg.reply.assert_not_called()
        submit.assert_not_called()

    async def test_untagged_messages_are_ignored(self):
        msg = _message("feedback: something long enough", mention=False)
        await _cog().on_message(msg)
        msg.reply.assert_not_called()


class TestFeedbackHelpers:
    def test_guess_type(self):
        assert feedback_intake.guess_type("the button is broken") == "bug_report"
        assert feedback_intake.guess_type("idea: dark mode") == "feature_request"
        assert feedback_intake.guess_type("love the site") == "general"

    def test_make_title_cuts_long_first_line(self):
        title = feedback_intake.make_title("x" * 200 + "\nsecond line")
        assert len(title) == 90 and title.endswith("…")

    def test_falls_back_to_site_api_keys(self, monkeypatch):
        import config
        monkeypatch.delattr(config, "WEB_APP_API_KEY", raising=False)
        monkeypatch.delenv("WEB_APP_API_KEY", raising=False)
        monkeypatch.setenv("API_KEYS", "first-key, second-key")
        assert feedback_intake._web_api_key() == "first-key"
