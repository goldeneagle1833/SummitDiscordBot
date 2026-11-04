"""Feedback channel -> Claude -> pull request -> owner DM with Merge / Close buttons.

Flow:
1. Someone posts in the feedback channel (CLAUDE_FEEDBACK_CHANNEL_ID).
2. Claude triages the message (services/feedback_triage.py):
   - not actionable (chatter, thanks)      -> ignored
   - clear, low-risk change                -> step 3 right away
   - risky / vague / suspicious            -> owner DM with "Send to Claude" / "Dismiss"
3. The bot files a GitHub issue labelled ``claude-feedback``. That label starts
   .github/workflows/claude-feedback.yml, where Claude Code makes the change and
   opens a PR from branch ``claude-feedback/issue-<n>``.
4. The bot polls GitHub. When the PR shows up it DMs the owner the request,
   Claude's analysis, the PR summary, files changed and CI status, with buttons:
   Merge, Request changes, Close PR, Refresh, plus links.
5. "Request changes" comments ``@claude <your notes>`` on the PR, which runs
   Claude again on the same branch; the bot DMs again when new commits land.
6. On merge, the bot replies to the original message to tell the submitter.

Buttons are DynamicItems, so they keep working after a bot restart.
"""

import datetime
import json
import logging
import os
import re

import discord
from discord.ext import commands, tasks

import config
from repositories import claude_feedback_repo as repo
from services.feedback_triage import TriageError, triage_feedback
from services.github_client import GitHubClient, GitHubError

logger = logging.getLogger("discord_bot")

DEFAULT_CHANNEL_ID = 1463363646146088963
DEFAULT_REPO = "goldeneagle1833/SummitDiscordBot"

LABEL = "claude-feedback"
NO_CHANGE_LABEL = "claude-no-change"
FAILED_LABEL = "claude-failed"
BRANCH_PREFIX = "claude-feedback/issue-"

MIN_LENGTH = 15
MAX_PER_USER_PER_DAY = 5
PR_WAIT_MINUTES = 90
POLL_SECONDS = 120

EMOJI_SEEN = "👀"
EMOJI_WORKING = "🛠️"
EMOJI_PR = "📬"
EMOJI_SHIPPED = "✅"

KIND_EMOJI = {"bug": "🐛", "feature": "✨", "improvement": "🔧", "question": "❓", "other": "📝"}


# ── settings ─────────────────────────────────────────────────────────


def channel_id() -> int:
    return int(getattr(config, "CLAUDE_FEEDBACK_CHANNEL_ID", 0) or DEFAULT_CHANNEL_ID)


def admin_ids() -> list[int]:
    ids = getattr(config, "CLAUDE_FEEDBACK_ADMIN_IDS", None) or [getattr(config, "OWNER_ID", 0)]
    return [int(i) for i in ids if i]


def github_repo() -> str:
    return getattr(config, "GITHUB_REPO", None) or os.getenv("GITHUB_REPO") or DEFAULT_REPO


def github_token() -> str:
    return getattr(config, "GITHUB_FEEDBACK_TOKEN", None) or os.getenv("GITHUB_FEEDBACK_TOKEN", "")


def anthropic_key() -> str:
    return getattr(config, "ANTHROPIC_API_KEY", None) or os.getenv("ANTHROPIC_API_KEY", "")


def is_admin(user_id: int) -> bool:
    return int(user_id) in admin_ids()


def github() -> GitHubClient:
    return GitHubClient(github_token(), github_repo())


def branch_for(issue_number: int) -> str:
    return f"{BRANCH_PREFIX}{issue_number}"


def _trim(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _quote(text: str | None, limit: int = 900) -> str:
    return "\n".join(f"> {line}" for line in _trim(text, limit).splitlines()) or "> (empty)"


def _age_minutes(iso: str) -> float:
    created = datetime.datetime.fromisoformat(iso)
    if created.tzinfo is None:
        created = created.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - created).total_seconds() / 60


def pr_references_issue(pr: dict, issue_number: int) -> bool:
    if (pr.get("head") or {}).get("ref") == branch_for(issue_number):
        return True
    body = pr.get("body") or ""
    pattern = rf"\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+#{issue_number}\b"
    return re.search(pattern, body, re.I) is not None


def build_issue_body(req: dict) -> str:
    attachments = json.loads(req.get("attachments") or "[]")
    lines = [
        req.get("details") or req.get("summary") or "",
        "",
        "---",
        "",
        f"**Submitted in Discord by** {req['author_name']} — [original message]({req['jump_url']})",
        "",
        "**Original message (untrusted user text):**",
        "",
        _quote(req["content"], 3500),
    ]
    if attachments:
        lines += ["", "**Attachments:**"] + [f"- {url}" for url in attachments]
    lines += [
        "",
        f"_Triage: {req.get('kind')} · area: {req.get('likely_area')} · "
        f"risk: {req.get('risk')} — {req.get('triage_reason') or ''}_",
        "",
        f"<!-- summit-feedback-request:{req['id']} -->",
    ]
    return "\n".join(lines)


# ── embeds and views ─────────────────────────────────────────────────


def request_fields(embed: discord.Embed, req: dict):
    kind = req.get("kind") or "other"
    embed.add_field(
        name="Requested by",
        value=f"<@{req['author_id']}> ({req.get('author_name') or 'unknown'})",
        inline=True,
    )
    embed.add_field(
        name="Type",
        value=f"{KIND_EMOJI.get(kind, '📝')} {kind} · {req.get('likely_area') or '?'} · risk {req.get('risk') or '?'}",
        inline=True,
    )
    embed.add_field(name="Original feedback", value=_trim(_quote(req["content"], 900), 1024), inline=False)


def approval_embed(req: dict) -> discord.Embed:
    embed = discord.Embed(
        title=_trim(f"Feedback needs your OK: {req.get('title') or 'Untitled'}", 256),
        description=_trim(req.get("summary"), 1500) or None,
        url=req.get("jump_url") or None,
        color=discord.Color.orange(),
    )
    request_fields(embed, req)
    if req.get("triage_reason"):
        embed.add_field(name="Why Claude didn't start", value=_trim(req["triage_reason"], 1024), inline=False)
    embed.set_footer(text=f"Request #{req['id']}")
    return embed


def approval_view(req: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(FeedbackButton("approve", req["id"]))
    view.add_item(FeedbackButton("dismiss", req["id"]))
    if req.get("jump_url"):
        view.add_item(discord.ui.Button(label="Original message", style=discord.ButtonStyle.link, url=req["jump_url"]))
    return view


def pr_embed(req: dict, pr: dict, files: list[dict] | None = None,
             checks: dict | None = None, headline: str | None = None) -> discord.Embed:
    state = "merged" if pr.get("merged") else pr.get("state", "open")
    color = {
        "merged": discord.Color.purple(),
        "closed": discord.Color.dark_grey(),
    }.get(state, discord.Color.green())
    embed = discord.Embed(
        title=_trim(f"PR #{pr['number']}: {pr.get('title', '')}", 256),
        url=pr.get("html_url"),
        description=_trim(
            (f"**{headline}**\n\n" if headline else "") + (req.get("summary") or ""), 2000
        ) or None,
        color=color,
    )
    request_fields(embed, req)

    body = re.sub(r"<!--.*?-->", "", pr.get("body") or "", flags=re.S).strip()
    if body:
        embed.add_field(name="What Claude changed", value=_trim(body, 1024), inline=False)

    changes = (
        f"{pr.get('changed_files', '?')} files · "
        f"+{pr.get('additions', '?')} / -{pr.get('deletions', '?')}"
    )
    if files:
        names = [f"`{f['filename']}`" for f in files[:8]]
        if len(files) > 8:
            names.append(f"…and {len(files) - 8} more")
        changes += "\n" + "\n".join(names)
    embed.add_field(name="Changes", value=_trim(changes, 1024), inline=False)

    if state == "open":
        if checks and checks["total"]:
            if checks["failed"]:
                ci = f"❌ {checks['failed']} failing, {checks['passed']} passed"
            elif checks["pending"]:
                ci = f"⏳ {checks['pending']} running, {checks['passed']} passed"
            else:
                ci = f"✅ all {checks['passed']} passed"
        else:
            ci = "No checks reported yet"
        embed.add_field(name="Checks", value=ci, inline=True)
        mergeable = pr.get("mergeable_state") or "unknown"
        embed.add_field(
            name="Mergeable",
            value={"clean": "✅ Ready", "dirty": "❌ Conflicts", "blocked": "⛔ Blocked",
                   "unstable": "⚠️ Checks not green", "behind": "↩️ Behind main"}.get(mergeable, mergeable),
            inline=True,
        )
    else:
        embed.add_field(name="Status", value="🟣 Merged" if state == "merged" else "⚫ Closed", inline=True)

    embed.set_footer(text=f"Request #{req['id']} · Issue #{req.get('issue_number')}")
    return embed


def pr_view(req: dict, pr: dict) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if pr.get("state") == "open" and not pr.get("merged"):
        view.add_item(FeedbackButton("merge", req["id"]))
        view.add_item(FeedbackButton("changes", req["id"]))
        view.add_item(FeedbackButton("close", req["id"]))
        view.add_item(FeedbackButton("refresh", req["id"]))
    url = pr.get("html_url")
    if url:
        view.add_item(discord.ui.Button(label="View PR", style=discord.ButtonStyle.link, url=url))
        view.add_item(discord.ui.Button(label="Files changed", style=discord.ButtonStyle.link, url=f"{url}/files"))
    if req.get("jump_url"):
        view.add_item(discord.ui.Button(label="Original message", style=discord.ButtonStyle.link, url=req["jump_url"]))
    return view


BUTTON_STYLES = {
    "merge": ("Merge", discord.ButtonStyle.success, "✅"),
    "changes": ("Request changes", discord.ButtonStyle.primary, "✏️"),
    "close": ("Close PR", discord.ButtonStyle.danger, "🗑️"),
    "refresh": ("Refresh", discord.ButtonStyle.secondary, "🔄"),
    "approve": ("Send to Claude", discord.ButtonStyle.success, "🤖"),
    "dismiss": ("Dismiss", discord.ButtonStyle.secondary, "✖️"),
}


class FeedbackButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"cfb:(?P<action>merge|changes|close|refresh|approve|dismiss):(?P<rid>\d+)",
):
    def __init__(self, action: str, request_id: int):
        self.action = action
        self.request_id = int(request_id)
        label, style, emoji = BUTTON_STYLES[action]
        super().__init__(
            discord.ui.Button(
                label=label, style=style, emoji=emoji,
                custom_id=f"cfb:{action}:{self.request_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match["action"], int(match["rid"]))

    async def callback(self, interaction: discord.Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message("Only the bot owner can use these buttons.", ephemeral=True)
            return
        cog = interaction.client.get_cog("ClaudeFeedbackCog")
        req = repo.get_request(self.request_id)
        if cog is None or req is None:
            await interaction.response.send_message("That request no longer exists.", ephemeral=True)
            return

        if self.action == "changes":
            if not req.get("pr_number"):
                await interaction.response.send_message("There's no PR for this yet.", ephemeral=True)
                return
            await interaction.response.send_modal(RequestChangesModal(cog, req))
        elif self.action in ("merge", "close"):
            await interaction.response.send_message(
                f"{'Squash-merge' if self.action == 'merge' else 'Close'} PR #{req.get('pr_number')}?",
                view=ConfirmView(cog, self.action, req, interaction.message),
                ephemeral=True,
            )
        elif self.action == "refresh":
            await interaction.response.defer()
            await cog.refresh_dm(req, interaction.message)
        elif self.action == "approve":
            await interaction.response.defer()
            await cog.approve(req, interaction.message, interaction.user)
        elif self.action == "dismiss":
            await interaction.response.defer()
            await cog.dismiss(req, interaction.message)


class ConfirmView(discord.ui.View):
    def __init__(self, cog, action: str, req: dict, dm_message):
        super().__init__(timeout=120)
        self.cog = cog
        self.action = action
        self.req = req
        self.dm_message = dm_message

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Working on it…", view=None)
        if self.action == "merge":
            result = await self.cog.merge(self.req, self.dm_message, interaction.user)
        else:
            result = await self.cog.close(self.req, self.dm_message, interaction.user)
        await interaction.edit_original_response(content=result)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", view=None)


class RequestChangesModal(discord.ui.Modal, title="Ask Claude for changes"):
    notes = discord.ui.TextInput(
        label="What should Claude change?",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        placeholder="e.g. Keep the old button label, and add a test for the empty-queue case.",
    )

    def __init__(self, cog, req: dict):
        super().__init__()
        self.cog = cog
        self.req = req

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await github().comment(
                self.req["pr_number"],
                f"@claude {self.notes.value}\n\n_Requested by {interaction.user} from Discord._",
            )
        except GitHubError as e:
            await interaction.response.send_message(f"Couldn't comment on the PR: {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            "Sent to Claude. I'll DM you when it pushes an update.", ephemeral=True
        )


# ── the cog ──────────────────────────────────────────────────────────


class ClaudeFeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._labels_ready = False
        repo.create_claude_feedback_table()
        if github_token():
            self.check_progress.start()
            logger.info(f"ClaudeFeedbackCog watching channel {channel_id()} for {github_repo()}")
        else:
            logger.warning("ClaudeFeedbackCog: GITHUB_FEEDBACK_TOKEN not set; feedback -> PR is off")

    def cog_unload(self):
        self.check_progress.cancel()

    # ── intake ───────────────────────────────────────────────────────

    def is_feedback_message(self, message: discord.Message) -> bool:
        if message.author.bot or message.guild is None:
            return False
        cid = channel_id()
        in_channel = message.channel.id == cid
        # Forum channel: only the first post of each thread counts
        forum_post = getattr(message.channel, "parent_id", None) == cid and message.id == message.channel.id
        if not (in_channel or forum_post):
            return False
        text = (message.content or "").strip()
        if text.startswith(("!", "/")):
            return False
        return len(text) >= MIN_LENGTH or bool(message.attachments)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not github_token() or not self.is_feedback_message(message):
            return
        try:
            await self.handle_feedback(message)
        except Exception as e:
            logger.error(f"Claude feedback: failed on message {message.id}: {e}", exc_info=True)

    async def handle_feedback(self, message: discord.Message):
        if not is_admin(message.author.id) and repo.count_recent_by_author(message.author.id) >= MAX_PER_USER_PER_DAY:
            await message.reply(
                "Thanks! You've hit today's limit for automatic fixes, so this one won't go to Claude. "
                "The team will still see it.",
                mention_author=False, delete_after=30,
            )
            return

        content = message.content or ""
        if isinstance(message.channel, discord.Thread) and message.id == message.channel.id:
            content = f"{message.channel.name}\n\n{content}".strip()
        images = [a.url for a in message.attachments if (a.content_type or "").startswith("image/")]
        request_id = repo.create_request(
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=message.guild.id if message.guild else None,
            author_id=message.author.id,
            author_name=message.author.display_name,
            content=content or "(attachment only)",
            attachments=json.dumps([a.url for a in message.attachments]),
            jump_url=message.jump_url,
        )
        if request_id is None:
            return
        await self._react(message, EMOJI_SEEN)

        try:
            result = await triage_feedback(
                content, message.author.display_name, images, api_key=anthropic_key() or None
            )
        except TriageError as e:
            logger.warning(f"Claude feedback triage failed for #{request_id}: {e}")
            result = {
                "actionable": True, "auto_proceed": False, "kind": "other",
                "title": _trim(content.splitlines()[0] if content else "Feedback", 80),
                "summary": _trim(content, 300), "details": content,
                "likely_area": "unknown", "risk": "medium",
                "reason": f"Automatic triage failed: {e}",
            }

        fields = dict(
            kind=result["kind"], title=_trim(result["title"], 120), summary=result["summary"],
            details=result["details"], likely_area=result["likely_area"], risk=result["risk"],
            triage_reason=result["reason"],
        )
        if not result["actionable"]:
            repo.update_request(request_id, status="skipped", **fields)
            await self._unreact(message, EMOJI_SEEN)
            return

        if result["auto_proceed"]:
            repo.update_request(request_id, **fields)
            await self.file_issue(request_id)
            await self._react(message, EMOJI_WORKING)
        else:
            repo.update_request(request_id, status="awaiting_approval", **fields)
            req = repo.get_request(request_id)
            await self.dm_admins(req, approval_embed(req), approval_view(req))

    async def file_issue(self, request_id: int) -> dict:
        req = repo.get_request(request_id)
        gh = github()
        if not self._labels_ready:
            await gh.ensure_label(LABEL, "7057ff", "Discord feedback for Claude to fix")
            await gh.ensure_label(NO_CHANGE_LABEL, "cfd3d7", "Claude decided no code change was needed")
            await gh.ensure_label(FAILED_LABEL, "d93f0b", "Claude's feedback run failed")
            self._labels_ready = True
        issue = await gh.create_issue(
            title=req.get("title") or "Discord feedback",
            body=build_issue_body(req),
            labels=[LABEL],
        )
        repo.update_request(request_id, status="issue_open", issue_number=issue["number"])
        logger.info(f"Claude feedback #{request_id}: filed issue #{issue['number']}")
        return issue

    # ── owner actions ────────────────────────────────────────────────

    async def approve(self, req: dict, dm_message, user):
        if req["status"] != "awaiting_approval":
            await dm_message.edit(view=None)
            return
        try:
            issue = await self.file_issue(req["id"])
        except GitHubError as e:
            repo.update_request(req["id"], error=str(e))
            await dm_message.reply(f"Couldn't file the issue: {e}")
            return
        embed = dm_message.embeds[0] if dm_message.embeds else approval_embed(req)
        embed.color = discord.Color.blurple()
        embed.add_field(
            name="Sent to Claude",
            value=f"[Issue #{issue['number']}]({issue['html_url']}) — I'll DM you when the PR is ready.",
            inline=False,
        )
        await dm_message.edit(embed=embed, view=None)
        message = await self._original_message(req)
        if message:
            await self._react(message, EMOJI_WORKING)

    async def dismiss(self, req: dict, dm_message):
        repo.update_request(req["id"], status="dismissed")
        embed = dm_message.embeds[0] if dm_message.embeds else approval_embed(req)
        embed.color = discord.Color.dark_grey()
        embed.add_field(name="Dismissed", value="Not sent to Claude.", inline=False)
        await dm_message.edit(embed=embed, view=None)
        message = await self._original_message(req)
        if message:
            await self._unreact(message, EMOJI_SEEN)

    async def merge(self, req: dict, dm_message, user) -> str:
        gh = github()
        try:
            pr = await gh.get_pr(req["pr_number"])
            if pr.get("merged"):
                await self._finish(req, pr, dm_message)
                return "Already merged."
            if pr.get("state") != "open":
                await self._finish(req, pr, dm_message)
                return "That PR is closed."
            await gh.merge_pr(pr["number"], "squash", sha=pr["head"]["sha"])
            await gh.delete_branch(pr["head"]["ref"])
            pr = await gh.get_pr(pr["number"])
        except GitHubError as e:
            return f"❌ Merge failed: {e.message}"
        await self._finish(req, pr, dm_message)
        logger.info(f"Claude feedback #{req['id']}: PR #{pr['number']} merged by {user}")
        return f"✅ Merged PR #{pr['number']}. Deploy runs automatically from main."

    async def close(self, req: dict, dm_message, user) -> str:
        gh = github()
        try:
            pr = await gh.get_pr(req["pr_number"])
            if pr.get("state") == "open":
                await gh.close_pr(pr["number"])
                await gh.delete_branch(pr["head"]["ref"])
                await gh.comment(pr["number"], f"Closed from Discord by {user}.")
            if req.get("issue_number"):
                await gh.close_issue(req["issue_number"], "not_planned")
            pr = await gh.get_pr(pr["number"])
        except GitHubError as e:
            return f"❌ Couldn't close: {e.message}"
        await self._finish(req, pr, dm_message)
        return f"Closed PR #{pr['number']}."

    async def refresh_dm(self, req: dict, dm_message):
        if not req.get("pr_number"):
            return
        try:
            embed, view, pr = await self._pr_message(req)
        except GitHubError as e:
            await dm_message.reply(f"Couldn't refresh: {e.message}")
            return
        if pr.get("merged") or pr.get("state") == "closed":
            await self._finish(req, pr, dm_message)
            return
        await dm_message.edit(embed=embed, view=view)

    # ── polling ──────────────────────────────────────────────────────

    @tasks.loop(seconds=POLL_SECONDS)
    async def check_progress(self):
        try:
            requests = repo.get_open_requests()
        except Exception as e:
            logger.error(f"Claude feedback: couldn't load open requests: {e}")
            return
        recent_prs = None
        for req in requests:
            try:
                if req["status"] == "issue_open":
                    if recent_prs is None:
                        recent_prs = await github().list_recent_prs()
                    await self._check_for_pr(req, recent_prs)
                elif req["status"] == "pr_open":
                    await self._check_pr(req)
            except GitHubError as e:
                logger.warning(f"Claude feedback #{req['id']}: GitHub error: {e}")
            except Exception as e:
                logger.error(f"Claude feedback #{req['id']}: poll error: {e}", exc_info=True)

    @check_progress.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def _check_for_pr(self, req: dict, recent_prs: list[dict]):
        issue_number = req["issue_number"]
        pr = next((p for p in recent_prs if pr_references_issue(p, issue_number)), None)
        if pr is None:
            pr = await github().find_pr_for_branch(branch_for(issue_number))
        if pr is not None:
            repo.update_request(
                req["id"], status="pr_open", pr_number=pr["number"],
                pr_url=pr["html_url"], head_sha=pr["head"]["sha"],
            )
            req = repo.get_request(req["id"])
            embed, view, _ = await self._pr_message(req, headline="Claude opened a pull request")
            await self.dm_admins(req, embed, view)
            message = await self._original_message(req)
            if message:
                await self._unreact(message, EMOJI_WORKING)
                await self._react(message, EMOJI_PR)
            return

        issue = await github().get_issue(issue_number)
        labels = {label["name"] for label in issue.get("labels", [])}
        if FAILED_LABEL in labels:
            why = "Claude's GitHub Actions run failed — see the issue for the run link."
        elif NO_CHANGE_LABEL in labels or issue.get("state") == "closed":
            why = "Claude decided no code change was needed."
        elif _age_minutes(req["updated_at"]) > PR_WAIT_MINUTES:
            why = f"No PR after {PR_WAIT_MINUTES} minutes — check the Actions run."
        else:
            why = None
        if why:
            repo.update_request(req["id"], status="no_pr")
            embed = discord.Embed(
                title=_trim(f"No PR for: {req.get('title')}", 256),
                url=issue.get("html_url"),
                description=f"{why}\nSee the issue for Claude's notes.",
                color=discord.Color.light_grey(),
            )
            request_fields(embed, req)
            embed.set_footer(text=f"Request #{req['id']} · Issue #{issue_number}")
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(label="View issue", style=discord.ButtonStyle.link, url=issue["html_url"]))
            await self.dm_admins(req, embed, view, store=False)

    async def _check_pr(self, req: dict):
        pr = await github().get_pr(req["pr_number"])
        if pr.get("merged") or pr.get("state") == "closed":
            await self._finish(req, pr, await self._stored_dm(req))
            return
        sha = pr["head"]["sha"]
        if sha != req.get("head_sha"):
            repo.update_request(req["id"], head_sha=sha)
            req = repo.get_request(req["id"])
            embed, view, _ = await self._pr_message(req, pr, headline="Claude pushed an update")
            await self.dm_admins(req, embed, view)

    # ── helpers ──────────────────────────────────────────────────────

    async def _pr_message(self, req: dict, pr: dict | None = None, headline: str | None = None):
        gh = github()
        if pr is None or "changed_files" not in pr:
            pr = await gh.get_pr(req["pr_number"])
        files, checks = [], None
        try:
            files = await gh.get_pr_files(pr["number"])
            checks = await gh.check_summary(pr["head"]["sha"])
        except GitHubError as e:
            logger.info(f"Claude feedback #{req['id']}: extra PR info unavailable: {e}")
        return pr_embed(req, pr, files, checks, headline), pr_view(req, pr), pr

    async def _finish(self, req: dict, pr: dict, dm_message):
        """Mark merged/closed, update the DM, and tell the submitter on merge."""
        merged = bool(pr.get("merged"))
        already = req["status"] in ("merged", "closed")
        repo.update_request(req["id"], status="merged" if merged else "closed")
        req = repo.get_request(req["id"])
        if dm_message is not None:
            try:
                await dm_message.edit(embed=pr_embed(req, pr), view=pr_view(req, pr))
            except discord.HTTPException as e:
                logger.info(f"Claude feedback #{req['id']}: couldn't edit DM: {e}")
        if already:
            return
        message = await self._original_message(req)
        if message is None:
            return
        await self._unreact(message, EMOJI_PR)
        if merged:
            await self._react(message, EMOJI_SHIPPED)
            try:
                await message.reply(
                    f"{EMOJI_SHIPPED} Thanks <@{req['author_id']}>! This was fixed in "
                    f"[PR #{pr['number']}](<{pr['html_url']}>) and is on its way to the live site/bot.",
                    mention_author=True,
                )
            except discord.HTTPException as e:
                logger.info(f"Claude feedback #{req['id']}: couldn't reply to submitter: {e}")

    async def dm_admins(self, req: dict, embed: discord.Embed, view: discord.ui.View, store: bool = True):
        first = None
        for uid in admin_ids():
            try:
                user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                sent = await user.send(embed=embed, view=view)
                first = first or sent
            except discord.HTTPException as e:
                logger.warning(f"Claude feedback: couldn't DM {uid}: {e}")
        if store and first is not None:
            repo.update_request(req["id"], dm_channel_id=str(first.channel.id), dm_message_id=str(first.id))

    async def _stored_dm(self, req: dict):
        if not req.get("dm_channel_id") or not req.get("dm_message_id"):
            return None
        try:
            channel = self.bot.get_channel(int(req["dm_channel_id"])) or await self.bot.fetch_channel(
                int(req["dm_channel_id"])
            )
            return channel.get_partial_message(int(req["dm_message_id"]))
        except discord.HTTPException:
            return None

    async def _original_message(self, req: dict):
        try:
            channel = self.bot.get_channel(int(req["channel_id"])) or await self.bot.fetch_channel(
                int(req["channel_id"])
            )
            return await channel.fetch_message(int(req["message_id"]))
        except (discord.HTTPException, AttributeError):
            return None

    async def _react(self, message, emoji: str):
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass

    async def _unreact(self, message, emoji: str):
        try:
            await message.remove_reaction(emoji, self.bot.user)
        except (discord.HTTPException, AttributeError):
            pass


async def setup(bot):
    await bot.add_cog(ClaudeFeedbackCog(bot))
