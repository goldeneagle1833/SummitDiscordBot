# Feedback → Claude → Pull Request

Messages in the feedback channel (`CLAUDE_FEEDBACK_CHANNEL_ID`, default
`1463363646146088963`) go through this flow:

1. **Triage**: Claude (`services/feedback_triage.py`) reads the message and any screenshots.
   - Chatter, thanks, or game questions: ignored.
   - A clear, low-risk bug or change: filed straight away.
   - Vague, risky, or suspicious requests (shop/auth/moderation changes, "ignore your instructions", and so on): the owner gets a DM with **Send to Claude** / **Dismiss**.
2. **Issue**: the bot opens a GitHub issue labelled `claude-feedback` and reacts 🛠️ on the message.
3. **PR**: `.github/workflows/claude-feedback.yml` has Claude make the change and run the tests. The workflow then opens a PR from `claude-feedback/issue-<n>`. Claude only gets file-edit and test tools. The workflow does the commit and push, and refuses any change under `.github/`.
4. **DM**: the bot polls GitHub every 2 minutes. When the PR appears it DMs the owner with the request, Claude's analysis, the PR description, the files changed, CI status and mergeability. The DM has these buttons:
   - **Merge**: squash-merges at the exact commit you reviewed. This deploys from main as usual.
   - **Request changes**: opens a box for your notes and posts `@claude <notes>` on the PR. Claude updates the branch, and you get a new DM when the commits land.
   - **Close PR**: closes the PR and the issue, and deletes the branch.
   - **Refresh**: re-checks CI and mergeability.
   - Links: View PR, Files changed, Original message.
5. **Done**: after a merge the bot replies to the original message to thank the submitter.

If Claude decides no change is needed, its run fails, or no PR appears within 90 minutes, you get a DM linking to the issue.

Each user can send 5 requests a day (admins have no limit). Buttons work only for `CLAUDE_FEEDBACK_ADMIN_IDS` (default `[OWNER_ID]`) and keep working after restarts.

## Setup

**Bot server** (`discord-bot/.env`):

```
GITHUB_FEEDBACK_TOKEN=github_pat_...   # fine-grained: Contents, Issues, Pull requests = Read and write on this repo
ANTHROPIC_API_KEY=sk-ant-...
```

The feature stays off until `GITHUB_FEEDBACK_TOKEN` is set. Optional `config.py` overrides: `CLAUDE_FEEDBACK_CHANNEL_ID`, `CLAUDE_FEEDBACK_ADMIN_IDS`, `GITHUB_REPO`.

**GitHub repo → Settings → Secrets and variables → Actions**:

- `ANTHROPIC_API_KEY`: used by the workflow.
- `FEEDBACK_PR_TOKEN`: the same token as `GITHUB_FEEDBACK_TOKEN`. PRs pushed with the default `GITHUB_TOKEN` don't trigger the PR test workflows, so set this.

The **Request changes** loop uses `anthropics/claude-code-action` in tag mode. It needs the Claude GitHub App installed on the repo (https://github.com/apps/claude).
