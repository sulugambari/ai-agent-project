"""Normalize the live GitHub Issues REST API into the CompanyDocument contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from company_assistant.connectors.github import load_github_issues
from company_assistant.models import CompanyDocument

GITHUB_API_BASE = "https://api.github.com"

FetchFailureReason = Literal[
    "rate_limited", "not_found", "unauthorized", "server_error", "network", "malformed"
]


class GitHubFetchError(Exception):
    """Raised when the live GitHub source cannot be trusted for this request.

    Carries a `reason` so callers can compose an honest disclosure message and
    decide to fall back, without re-inspecting the underlying httpx exception.
    """

    def __init__(self, reason: FetchFailureReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class _GitHubUser(BaseModel):
    login: str


class _GitHubLabel(BaseModel):
    name: str


class _LiveIssue(BaseModel):
    """Schema for one item in the GitHub Issues REST API response.

    The issues endpoint also returns pull requests; a `pull_request` key
    distinguishes them so the caller can skip non-issue records.
    """

    node_id: str
    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    user: _GitHubUser
    assignees: list[_GitHubUser] = Field(default_factory=list)
    labels: list[_GitHubLabel] = Field(default_factory=list)
    updated_at: datetime
    pull_request: dict | None = None


def _classify_http_error(exc: httpx.HTTPStatusError) -> GitHubFetchError:
    response = exc.response
    status = response.status_code
    if status == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        return GitHubFetchError("rate_limited", f"rate limit exceeded ({response.url})")
    if status == 404:
        return GitHubFetchError("not_found", f"repository not found ({response.url})")
    if status in (401, 403):
        return GitHubFetchError("unauthorized", f"HTTP {status} ({response.url})")
    if status >= 500:
        return GitHubFetchError("server_error", f"HTTP {status} ({response.url})")
    return GitHubFetchError("server_error", f"unexpected HTTP {status} ({response.url})")


def _issue_to_document(issue: _LiveIssue, *, repo: str, fetched_at: datetime) -> CompanyDocument:
    details = (
        f"State: {issue.state}\n"
        f"Labels: {', '.join(label.name for label in issue.labels)}\n"
        f"Assignees: {', '.join(a.login for a in issue.assignees) or 'Unassigned'}\n\n"
        f"{issue.body or ''}"
    )
    return CompanyDocument(
        source_id=f"GH-LIVE-{issue.number}",
        source_type="github",
        title=f"Issue #{issue.number}: {issue.title}",
        content=details,
        source_path=issue.html_url,
        allowed_roles=frozenset({"engineering"}),
        author=issue.user.login,
        occurred_at=issue.updated_at,
        metadata={
            "number": issue.number,
            "state": issue.state,
            "node_id": issue.node_id,
            "html_url": issue.html_url,
            "repository": repo,
            "source_freshness": "live",
            "fetched_at": fetched_at.isoformat(),
        },
    )


def fetch_live_issues(
    repo: str,
    token: str | None = None,
    *,
    client: httpx.Client | None = None,
    base_url: str = GITHUB_API_BASE,
    per_page: int = 100,
    timeout: float = 10.0,
) -> list[CompanyDocument]:
    """Fetch every issue from `repo`, paginated, and normalize it.

    `client` lets tests inject a `httpx.MockTransport`-backed client without a
    network call; production code leaves it unset. Raises `GitHubFetchError` on
    any failure - malformed response, HTTP error, or network error. Never
    returns a partial result silently: a failure on any page aborts the fetch.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    fetched_at = datetime.now(timezone.utc)
    documents: list[CompanyDocument] = []
    owns_client = client is None
    http_client = client or httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    try:
        page = 1
        while True:
            try:
                response = http_client.get(
                    f"/repos/{repo}/issues",
                    params={"state": "all", "per_page": per_page, "page": page},
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _classify_http_error(exc) from exc
            except httpx.RequestError as exc:
                raise GitHubFetchError("network", str(exc)) from exc

            try:
                raw_items = response.json()
            except json.JSONDecodeError as exc:
                raise GitHubFetchError(
                    "malformed", f"response body was not valid JSON: {exc}"
                ) from exc

            if not isinstance(raw_items, list):
                raise GitHubFetchError(
                    "malformed",
                    f"expected a JSON array of issues, got {type(raw_items).__name__}",
                )

            for raw_item in raw_items:
                try:
                    issue = _LiveIssue.model_validate(raw_item)
                except ValidationError as exc:
                    number = raw_item.get("number", "?") if isinstance(raw_item, dict) else "?"
                    raise GitHubFetchError("malformed", f"issue #{number}: {exc}") from exc
                if issue.pull_request is not None:
                    continue
                documents.append(_issue_to_document(issue, repo=repo, fetched_at=fetched_at))

            if len(raw_items) < per_page:
                break
            page += 1
    finally:
        if owns_client:
            http_client.close()

    return documents


@dataclass(frozen=True)
class GitHubLoadResult:
    """Outcome of loading GitHub work items - live or degraded to fallback.

    `source_freshness` and `detail` let the caller disclose the degraded state
    to the user; the same freshness is also stamped into every document's own
    metadata, so it survives even if a caller only looks at individual records.
    """

    documents: list[CompanyDocument]
    source_freshness: Literal["live", "fallback"]
    detail: str


def load_github_live_issues(
    repo: str,
    token: str | None = None,
    *,
    fallback_dir: Path = Path("data/raw/github"),
    **fetch_kwargs: object,
) -> GitHubLoadResult:
    """Fetch live GitHub issues; fall back to the local export on failure.

    Never presents fallback data as live: every returned document's metadata
    carries an accurate `source_freshness`, and the result reports it at the
    batch level too. Only `GitHubFetchError` triggers the fallback - if the
    fallback read itself fails (e.g. a missing directory), that propagates
    instead of being silently swallowed, since at that point neither source
    can be trusted and hiding it would be exactly the fabricated-freshness
    failure this step exists to prevent.
    """
    try:
        documents = fetch_live_issues(repo, token, **fetch_kwargs)
    except GitHubFetchError as exc:
        fetched_at = datetime.now(timezone.utc)
        fallback_documents = [
            doc.model_copy(
                update={
                    "metadata": {
                        **doc.metadata,
                        "source_freshness": "fallback",
                        "fetched_at": fetched_at.isoformat(),
                    }
                }
            )
            for doc in load_github_issues(fallback_dir)
        ]
        detail = (
            f"live GitHub source unavailable ({exc.reason}: {exc.detail}) - "
            f"showing local snapshot from '{fallback_dir}' instead"
        )
        return GitHubLoadResult(fallback_documents, "fallback", detail)

    return GitHubLoadResult(
        documents, "live", f"fetched {len(documents)} issue(s) live from {repo}"
    )
