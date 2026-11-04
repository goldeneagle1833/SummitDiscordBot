"""Small async GitHub REST client used by the Claude feedback pipeline.

Needs a token with Contents, Issues and Pull requests read/write on the repo
(a fine-grained personal access token works).
"""

import logging

import aiohttp

logger = logging.getLogger("discord_bot")

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub {status}: {message}")
        self.status = status
        self.message = message


class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.token = token
        self.repo = repo  # "owner/name"
        self.owner = repo.split("/")[0]

    async def _request(self, method: str, path: str, *, json=None, params=None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "summit-discord-bot",
        }
        url = path if path.startswith("http") else f"{API}{path}"
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, headers=headers, json=json, params=params
            ) as resp:
                if resp.status == 204:
                    return None
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = None
                if resp.status >= 400:
                    msg = (data or {}).get("message") if isinstance(data, dict) else None
                    raise GitHubError(resp.status, msg or resp.reason or "error")
                return data

    # ── labels / issues ──────────────────────────────────────────────

    async def ensure_label(self, name: str, color: str, description: str = ""):
        try:
            await self._request(
                "POST", f"/repos/{self.repo}/labels",
                json={"name": name, "color": color, "description": description},
            )
        except GitHubError as e:
            if e.status != 422:  # 422 = already exists
                raise

    async def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return await self._request(
            "POST", f"/repos/{self.repo}/issues",
            json={"title": title, "body": body, "labels": labels},
        )

    async def get_issue(self, number: int) -> dict:
        return await self._request("GET", f"/repos/{self.repo}/issues/{number}")

    async def comment(self, number: int, body: str) -> dict:
        """Comment on an issue or pull request."""
        return await self._request(
            "POST", f"/repos/{self.repo}/issues/{number}/comments", json={"body": body}
        )

    async def close_issue(self, number: int, reason: str = "not_planned"):
        return await self._request(
            "PATCH", f"/repos/{self.repo}/issues/{number}",
            json={"state": "closed", "state_reason": reason},
        )

    # ── pull requests ────────────────────────────────────────────────

    async def find_pr_for_branch(self, branch: str) -> dict | None:
        prs = await self._request(
            "GET", f"/repos/{self.repo}/pulls",
            params={"head": f"{self.owner}:{branch}", "state": "all", "per_page": 5},
        )
        return prs[0] if prs else None

    async def list_recent_prs(self, per_page: int = 30) -> list[dict]:
        return await self._request(
            "GET", f"/repos/{self.repo}/pulls",
            params={"state": "all", "sort": "created", "direction": "desc",
                    "per_page": per_page},
        ) or []

    async def get_pr(self, number: int) -> dict:
        return await self._request("GET", f"/repos/{self.repo}/pulls/{number}")

    async def get_pr_files(self, number: int) -> list[dict]:
        return await self._request(
            "GET", f"/repos/{self.repo}/pulls/{number}/files", params={"per_page": 100}
        ) or []

    async def merge_pr(self, number: int, method: str = "squash", sha: str | None = None):
        payload = {"merge_method": method}
        if sha:
            payload["sha"] = sha
        return await self._request(
            "PUT", f"/repos/{self.repo}/pulls/{number}/merge", json=payload
        )

    async def close_pr(self, number: int):
        return await self._request(
            "PATCH", f"/repos/{self.repo}/pulls/{number}", json={"state": "closed"}
        )

    async def delete_branch(self, branch: str):
        try:
            await self._request("DELETE", f"/repos/{self.repo}/git/refs/heads/{branch}")
        except GitHubError as e:
            logger.info(f"Could not delete branch {branch}: {e}")

    async def check_summary(self, sha: str) -> dict:
        """Count check runs on a commit: {'total', 'passed', 'failed', 'pending'}."""
        data = await self._request(
            "GET", f"/repos/{self.repo}/commits/{sha}/check-runs", params={"per_page": 100}
        ) or {}
        summary = {"total": 0, "passed": 0, "failed": 0, "pending": 0}
        for run in data.get("check_runs", []):
            summary["total"] += 1
            if run.get("status") != "completed":
                summary["pending"] += 1
            elif run.get("conclusion") in ("success", "neutral", "skipped"):
                summary["passed"] += 1
            else:
                summary["failed"] += 1
        return summary
