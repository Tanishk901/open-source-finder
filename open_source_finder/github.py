"""Fetch open issues from the GitHub REST API (standard library only).

Set GITHUB_TOKEN to raise the rate limit from 60 to 5,000 requests an hour.
"""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

API = "https://api.github.com"
BODY_CHARS = 3000      # keep Jev requests small and cheap
COMMENT_CHARS = 500
RECENT_COMMENTS = 5


class GitHubError(Exception):
    pass


@dataclass
class Issue:
    number: int
    title: str
    body: str
    labels: list[str]
    url: str
    age_days: int
    comment_count: int
    recent_comments: list[str] = field(default_factory=list)


@dataclass
class Repo:
    full_name: str
    description: str
    language: str


def _get(path):
    request = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "open-source-finder",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise GitHubError(f"Not found: {path}. Check the owner/repo name.") from error
        if error.code == 401:
            raise GitHubError("GitHub rejected GITHUB_TOKEN: it is wrong, expired, or revoked. "
                              "Create a new one, or remove it from .env to run without a token.") from error
        rate_limited = error.code == 429 or error.headers.get("X-RateLimit-Remaining") == "0"
        if error.code == 403 and not rate_limited:
            raise GitHubError(f"GitHub refused access to {path} (403). If you set GITHUB_TOKEN, check that it "
                              "can read public repositories.") from error
        if rate_limited:
            reset = error.headers.get("X-RateLimit-Reset")
            when = ""
            if reset:
                minutes = max(1, -(-(int(reset) - int(datetime.now(timezone.utc).timestamp())) // 60))
                when = f" It resets in about {minutes} minute(s)."
            hint = "" if os.environ.get("GITHUB_TOKEN") else " Set GITHUB_TOKEN in .env to raise the limit to 5,000/hour."
            raise GitHubError(f"GitHub rate limit hit.{when}{hint}") from error
        raise GitHubError(f"GitHub returned {error.code} for {path}") from error
    except urllib.error.URLError as error:
        raise GitHubError(f"Could not reach GitHub: {error.reason}") from error


REPO_NAME = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def parse_repo(text):
    """Accept `owner/name`, a GitHub URL (including /issues/... links), or a .git clone URL."""
    path = text.strip()
    path = re.sub(r"^(https?://)?(www\.)?github\.com/", "", path)
    path = re.sub(r"^git@github\.com:", "", path)
    path = "/".join(path.strip("/").split("/")[:2])
    path = re.sub(r"\.git$", "", path)
    if not REPO_NAME.match(path):
        raise GitHubError(f"'{text}' is not a GitHub repo. Use owner/name, e.g. rust-lang/rustlings.")
    return path


def fetch_repo(full_name):
    data = _get(f"/repos/{full_name}")
    return Repo(full_name=data["full_name"], description=data.get("description") or "",
                language=data.get("language") or "unknown")


def fetch_issues(full_name, max_issues):
    """Open, unassigned issues (pull requests excluded), newest first, with their latest comments."""
    issues = []
    page = 1
    while len(issues) < max_issues:
        batch = _get(f"/repos/{full_name}/issues?state=open&per_page=100&page={page}")
        if not batch:
            break
        for raw in batch:
            if "pull_request" in raw or raw.get("assignees"):
                continue
            issues.append(_to_issue(raw))
            if len(issues) == max_issues:
                break
        page += 1

    for issue in issues:
        if issue.comment_count:
            issue.recent_comments = _recent_comments(full_name, issue)
    return issues


def _recent_comments(full_name, issue):
    # Comments come oldest first; jump to the last page so we get the newest ones.
    last_page = max(1, -(-issue.comment_count // 100))
    comments = _get(f"/repos/{full_name}/issues/{issue.number}/comments?per_page=100&page={last_page}")
    return [_clip(c.get("body") or "", COMMENT_CHARS) for c in comments[-RECENT_COMMENTS:]]


def _to_issue(raw):
    created = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
    return Issue(
        number=raw["number"],
        title=raw["title"],
        body=_clip(raw.get("body") or "", BODY_CHARS),
        labels=[label["name"] for label in raw.get("labels", [])],
        url=raw["html_url"],
        age_days=(datetime.now(timezone.utc) - created).days,
        comment_count=raw.get("comments", 0),
    )


def _clip(text, limit):
    return text if len(text) <= limit else text[:limit] + " [...]"
