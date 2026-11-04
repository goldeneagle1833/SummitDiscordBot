"""Tests for the feedback channel -> Claude -> PR -> owner DM pipeline."""

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cogs.claude_feedback as cf
import services.feedback_triage as triage_mod
from repositories import claude_feedback_repo as repo

OWNER = 111111111111111111
AUTHOR = 222222222222222222
CHANNEL = 333333333333333333


@pytest.fixture(autouse=True)
def _setup():
    repo.create_claude_feedback_table()
    with patch.object(cf.config, "OWNER_ID", OWNER, create=True), \
         patch.object(cf.config, "CLAUDE_FEEDBACK_ADMIN_IDS", None, create=True), \
         patch.object(cf.config, "CLAUDE_FEEDBACK_CHANNEL_ID", CHANNEL, create=True):
        yield


def _cog():
    bot = MagicMock()
    bot.user = MagicMock()
    with patch.object(cf, "github_token", return_value=""):
        return cf.ClaudeFeedbackCog(bot)


def _message(content="The leaderboard page crashes when I sort by wins", *, author_id=AUTHOR,
             channel_id=CHANNEL, bot=False):
    msg = MagicMock()
    msg.id = 999
    msg.content = content
    msg.author.id = author_id
    msg.author.bot = bot
    msg.author.display_name = "Tester"
    msg.guild.id = 1
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.id = channel_id
    msg.attachments = []
    msg.jump_url = "https://discord.com/channels/1/2/999"
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    msg.reply = AsyncMock()
    return msg


def _triage(**overrides):
    result = {
        "actionable": True, "kind": "bug", "title": "Fix leaderboard sort crash",
        "summary": "Sorting by wins crashes the page.", "details": "Details here",
        "likely_area": "web-app", "risk": "low", "auto_proceed": True, "reason": "Clear bug",
    }
    result.update(overrides)
    return result


def _new_request(**fields):
    rid = repo.create_request(
        message_id=fields.pop("message_id", 555), channel_id=CHANNEL, guild_id=1,
        author_id=AUTHOR, author_name="Tester", content="Sort by wins crashes",
        attachments="[]", jump_url="https://discord.com/channels/1/2/555",
    )
    if fields:
        repo.update_request(rid, **fields)
    return rid


def _pr(number=42, state="open", merged=False, sha="abc", body="Fixed it\n\nCloses #7"):
    return {
        "number": number, "state": state, "merged": merged, "title": "Fix sort crash",
        "html_url": f"https://github.com/o/r/pull/{number}", "body": body,
        "head": {"sha": sha, "ref": "claude-feedback/issue-7"},
        "changed_files": 2, "additions": 10, "deletions": 3, "mergeable_state": "clean",
    }


# ── repository ───────────────────────────────────────────────────────


def test_create_request_is_idempotent_per_message():
    assert _new_request() is not None
    assert repo.create_request(
        message_id=555, channel_id=CHANNEL, guild_id=1, author_id=AUTHOR,
        author_name="x", content="y", attachments="[]", jump_url="",
    ) is None


def test_open_requests_and_rate_count():
    a = _new_request(message_id=1, status="issue_open")
    _new_request(message_id=2, status="skipped")
    c = _new_request(message_id=3, status="pr_open")
    assert [r["id"] for r in repo.get_open_requests()] == [a, c]
    assert repo.count_recent_by_author(AUTHOR) == 2  # skipped ones don't count


def test_update_rejects_unknown_fields():
    rid = _new_request()
    with pytest.raises(ValueError):
        repo.update_request(rid, content="nope")


# ── helpers ──────────────────────────────────────────────────────────


def test_pr_references_issue():
    assert cf.pr_references_issue({"head": {"ref": "claude-feedback/issue-7"}, "body": ""}, 7)
    assert cf.pr_references_issue({"head": {"ref": "x"}, "body": "Closes #7"}, 7)
    assert cf.pr_references_issue({"head": {"ref": "x"}, "body": "fixes #7."}, 7)
    assert not cf.pr_references_issue({"head": {"ref": "x"}, "body": "see #7"}, 7)
    assert not cf.pr_references_issue({"head": {"ref": "x"}, "body": "Closes #70"}, 7)


def test_issue_body_quotes_message_and_tags_request():
    rid = _new_request(details="Bug details", kind="bug", likely_area="web-app", risk="low")
    body = cf.build_issue_body(repo.get_request(rid))
    assert "Bug details" in body
    assert "> Sort by wins crashes" in body
    assert f"<!-- summit-feedback-request:{rid} -->" in body


def test_pr_embed_and_view():
    rid = _new_request(issue_number=7, pr_number=42, summary="Sorting crashes")
    req = repo.get_request(rid)
    embed = cf.pr_embed(req, _pr(), [{"filename": "a.py"}], {"total": 2, "passed": 2, "failed": 0, "pending": 0})
    assert "PR #42" in embed.title
    assert any(f.name == "Checks" and "passed" in f.value for f in embed.fields)
    ids = [getattr(i, "custom_id", None) for i in cf.pr_view(req, _pr()).children]
    assert f"cfb:merge:{rid}" in ids and f"cfb:close:{rid}" in ids
    # Finished PRs only keep link buttons
    done = cf.pr_view(req, _pr(state="closed", merged=True))
    assert all(i.style == discord.ButtonStyle.link for i in done.children)


# ── intake ───────────────────────────────────────────────────────────


def test_is_feedback_message_filters():
    cog = _cog()
    assert cog.is_feedback_message(_message())
    assert not cog.is_feedback_message(_message(bot=True))
    assert not cog.is_feedback_message(_message(channel_id=123))
    assert not cog.is_feedback_message(_message("too short"))
    assert not cog.is_feedback_message(_message("!somecommand with a long argument"))


@pytest.mark.asyncio
async def test_clear_request_files_issue():
    cog = _cog()
    gh = MagicMock()
    gh.ensure_label = AsyncMock()
    gh.create_issue = AsyncMock(return_value={"number": 7, "html_url": "u"})
    msg = _message()
    with patch.object(cf, "triage_feedback", AsyncMock(return_value=_triage())), \
         patch.object(cf, "github", return_value=gh):
        await cog.handle_feedback(msg)
    req = repo.get_request(1)
    assert req["status"] == "issue_open"
    assert req["issue_number"] == 7
    assert gh.create_issue.call_args.kwargs["labels"] == [cf.LABEL]
    msg.add_reaction.assert_any_call(cf.EMOJI_WORKING)


@pytest.mark.asyncio
async def test_chatter_is_skipped():
    cog = _cog()
    msg = _message("thanks everyone for the great tournament!")
    with patch.object(cf, "triage_feedback", AsyncMock(return_value=_triage(actionable=False, auto_proceed=False))), \
         patch.object(cf, "github") as gh:
        await cog.handle_feedback(msg)
    assert repo.get_request(1)["status"] == "skipped"
    gh.assert_not_called()


@pytest.mark.asyncio
async def test_risky_request_asks_owner():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    with patch.object(cf, "triage_feedback", AsyncMock(return_value=_triage(auto_proceed=False, risk="high"))), \
         patch.object(cf, "github") as gh:
        await cog.handle_feedback(_message())
    assert repo.get_request(1)["status"] == "awaiting_approval"
    gh.assert_not_called()
    embed, view = cog.dm_admins.call_args.args[1:3]
    assert "needs your OK" in embed.title
    assert "cfb:approve:1" in [getattr(i, "custom_id", None) for i in view.children]


@pytest.mark.asyncio
async def test_triage_failure_falls_back_to_owner_approval():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    with patch.object(cf, "triage_feedback", AsyncMock(side_effect=cf.TriageError("down"))):
        await cog.handle_feedback(_message())
    req = repo.get_request(1)
    assert req["status"] == "awaiting_approval"
    assert "down" in req["triage_reason"]


@pytest.mark.asyncio
async def test_rate_limit():
    cog = _cog()
    for i in range(cf.MAX_PER_USER_PER_DAY):
        _new_request(message_id=1000 + i, status="issue_open")
    msg = _message()
    with patch.object(cf, "triage_feedback", AsyncMock()) as t:
        await cog.handle_feedback(msg)
    t.assert_not_called()
    msg.reply.assert_awaited()


# ── polling ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_finds_pr_and_dms_owner():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    cog._original_message = AsyncMock(return_value=None)
    rid = _new_request(status="issue_open", issue_number=7)
    gh = MagicMock()
    gh.get_pr = AsyncMock(return_value=_pr())
    gh.get_pr_files = AsyncMock(return_value=[])
    gh.check_summary = AsyncMock(return_value={"total": 0, "passed": 0, "failed": 0, "pending": 0})
    with patch.object(cf, "github", return_value=gh):
        await cog._check_for_pr(repo.get_request(rid), [_pr()])
    req = repo.get_request(rid)
    assert req["status"] == "pr_open" and req["pr_number"] == 42
    cog.dm_admins.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_reports_no_change():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    rid = _new_request(status="issue_open", issue_number=7)
    gh = MagicMock()
    gh.find_pr_for_branch = AsyncMock(return_value=None)
    gh.get_issue = AsyncMock(return_value={"state": "open", "html_url": "u",
                                           "labels": [{"name": cf.NO_CHANGE_LABEL}]})
    with patch.object(cf, "github", return_value=gh):
        await cog._check_for_pr(repo.get_request(rid), [])
    assert repo.get_request(rid)["status"] == "no_pr"
    assert "no code change" in cog.dm_admins.call_args.args[1].description


@pytest.mark.asyncio
async def test_poll_keeps_waiting_before_timeout():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    rid = _new_request(status="issue_open", issue_number=7)
    gh = MagicMock()
    gh.find_pr_for_branch = AsyncMock(return_value=None)
    gh.get_issue = AsyncMock(return_value={"state": "open", "html_url": "u", "labels": []})
    with patch.object(cf, "github", return_value=gh):
        await cog._check_for_pr(repo.get_request(rid), [])
    assert repo.get_request(rid)["status"] == "issue_open"
    cog.dm_admins.assert_not_called()


@pytest.mark.asyncio
async def test_merged_pr_thanks_submitter_once():
    cog = _cog()
    rid = _new_request(status="pr_open", issue_number=7, pr_number=42, head_sha="abc")
    original = _message()
    cog._original_message = AsyncMock(return_value=original)
    cog._stored_dm = AsyncMock(return_value=None)
    gh = MagicMock()
    gh.get_pr = AsyncMock(return_value=_pr(state="closed", merged=True))
    with patch.object(cf, "github", return_value=gh):
        await cog._check_pr(repo.get_request(rid))
        await cog._finish(repo.get_request(rid), _pr(state="closed", merged=True), None)
    assert repo.get_request(rid)["status"] == "merged"
    original.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_commits_send_update_dm():
    cog = _cog()
    cog.dm_admins = AsyncMock()
    rid = _new_request(status="pr_open", issue_number=7, pr_number=42, head_sha="old")
    gh = MagicMock()
    gh.get_pr = AsyncMock(return_value=_pr(sha="new"))
    gh.get_pr_files = AsyncMock(return_value=[])
    gh.check_summary = AsyncMock(return_value={"total": 0, "passed": 0, "failed": 0, "pending": 0})
    with patch.object(cf, "github", return_value=gh):
        await cog._check_pr(repo.get_request(rid))
    assert repo.get_request(rid)["head_sha"] == "new"
    assert "pushed an update" in cog.dm_admins.call_args.args[1].description


# ── owner actions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_merge_squashes_at_reviewed_sha():
    cog = _cog()
    cog._original_message = AsyncMock(return_value=None)
    rid = _new_request(status="pr_open", issue_number=7, pr_number=42)
    gh = MagicMock()
    gh.get_pr = AsyncMock(side_effect=[_pr(sha="abc"), _pr(state="closed", merged=True)])
    gh.merge_pr = AsyncMock()
    gh.delete_branch = AsyncMock()
    dm = MagicMock()
    dm.edit = AsyncMock()
    with patch.object(cf, "github", return_value=gh):
        result = await cog.merge(repo.get_request(rid), dm, "owner")
    gh.merge_pr.assert_awaited_once_with(42, "squash", sha="abc")
    assert "Merged" in result
    assert repo.get_request(rid)["status"] == "merged"
    dm.edit.assert_awaited()


@pytest.mark.asyncio
async def test_merge_failure_reports_error():
    cog = _cog()
    rid = _new_request(status="pr_open", pr_number=42)
    gh = MagicMock()
    gh.get_pr = AsyncMock(return_value=_pr())
    gh.merge_pr = AsyncMock(side_effect=cf.GitHubError(405, "Pull Request is not mergeable"))
    with patch.object(cf, "github", return_value=gh):
        result = await cog.merge(repo.get_request(rid), MagicMock(), "owner")
    assert "not mergeable" in result
    assert repo.get_request(rid)["status"] == "pr_open"


@pytest.mark.asyncio
async def test_buttons_are_owner_only():
    button = cf.FeedbackButton("merge", 1)
    interaction = MagicMock()
    interaction.user.id = AUTHOR
    interaction.response.send_message = AsyncMock()
    await button.callback(interaction)
    assert "Only the bot owner" in interaction.response.send_message.call_args.args[0]


@pytest.mark.asyncio
async def test_request_changes_comments_at_claude():
    rid = _new_request(status="pr_open", pr_number=42)
    modal = cf.RequestChangesModal(MagicMock(), repo.get_request(rid))
    modal.notes._value = "Add a test please"
    interaction = MagicMock()
    interaction.user = "owner"
    interaction.response.send_message = AsyncMock()
    gh = MagicMock()
    gh.comment = AsyncMock()
    with patch.object(cf, "github", return_value=gh):
        await modal.on_submit(interaction)
    number, body = gh.comment.call_args.args
    assert number == 42 and body.startswith("@claude Add a test please")


# ── triage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_never_auto_proceeds_on_high_risk():
    payload = _triage(risk="high", auto_proceed=True)
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
    )
    client = MagicMock()
    client.beta.messages.create = AsyncMock(return_value=response)
    with patch.object(triage_mod.anthropic, "AsyncAnthropic", return_value=client):
        result = await triage_mod.triage_feedback("drop the users table", "x", api_key="k")
    assert result["auto_proceed"] is False
    kwargs = client.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.asyncio
async def test_triage_refusal_raises():
    response = SimpleNamespace(stop_reason="refusal", content=[])
    client = MagicMock()
    client.beta.messages.create = AsyncMock(return_value=response)
    with patch.object(triage_mod.anthropic, "AsyncAnthropic", return_value=client):
        with pytest.raises(triage_mod.TriageError):
            await triage_mod.triage_feedback("x", "y", api_key="k")
