"""Async GitHub REST API client using httpx.

Features:
- Shared AsyncClient with connection pooling
- Automatic retry with exponential backoff for transient errors
- Configurable timeout via GITHUB_TIMEOUT env var
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass

import httpx

_GITHUB_API = "https://api.github.com"
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # seconds: 1, 2, 4

log = logging.getLogger("context7-local")

_TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)


@dataclass(frozen=True, slots=True)
class RepoInfo:
    """Minimal repository metadata returned by search."""

    owner: str
    repo: str
    description: str
    stars: int
    language: str

    @property
    def library_id(self) -> str:
        return f"/{self.owner}/{self.repo}"


def _timeout() -> float:
    return float(os.environ.get("GITHUB_TIMEOUT", "30"))


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _make_client() -> httpx.AsyncClient:
    """Create a shared AsyncClient (caller manages lifecycle)."""
    return httpx.AsyncClient(
        base_url=_GITHUB_API,
        headers=_headers(),
        timeout=_timeout(),
    )


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: object,
) -> httpx.Response:
    """Execute an HTTP request with automatic retry on transient errors.

    Retries up to _MAX_RETRIES times with exponential backoff (1s, 2s, 4s).
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.request(method, url, **kwargs)
            return resp
        except _TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_BASE * (2**attempt)
                log.warning(
                    "Retry %d/%d for %s %s: %s (wait %.1fs)",
                    attempt + 1,
                    _MAX_RETRIES,
                    method,
                    url,
                    type(exc).__name__,
                    wait,
                )
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


async def search_repositories(query: str, max_results: int = 5) -> list[RepoInfo]:
    """Search GitHub repositories by name/keyword.

    Returns up to *max_results* matches sorted by stars.
    """
    async with _make_client() as client:
        resp = await _request_with_retry(
            client,
            "GET",
            "/search/repositories",
            params={"q": query, "per_page": max_results, "sort": "stars"},
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            RepoInfo(
                owner=item["owner"]["login"],
                repo=item["name"],
                description=item.get("description") or "",
                stars=item.get("stargazers_count", 0),
                language=item.get("language") or "Unknown",
            )
            for item in items
        ]


async def fetch_readme(owner: str, repo: str) -> str | None:
    """Fetch the decoded README content for a repository."""
    async with _make_client() as client:
        resp = await _request_with_retry(client, "GET", f"/repos/{owner}/{repo}/readme")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return _decode_content(data)


async def list_docs_directory(
    owner: str, repo: str, path: str = "docs", max_depth: int = 2
) -> list[dict[str, str]]:
    """List Markdown files under a docs directory (depth ≤ *max_depth*).

    Returns a list of dicts with ``path`` and ``sha`` keys.
    """
    results: list[dict[str, str]] = []
    async with _make_client() as client:
        await _walk_tree(client, owner, repo, path, max_depth, 0, results)
    return results


async def _walk_tree(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    max_depth: int,
    current_depth: int,
    acc: list[dict[str, str]],
) -> None:
    if current_depth >= max_depth:
        return
    resp = await _request_with_retry(client, "GET", f"/repos/{owner}/{repo}/contents/{path}")
    if resp.status_code == 404:
        return
    resp.raise_for_status()
    items = resp.json()
    if not isinstance(items, list):
        return
    for item in items:
        if item["type"] == "file" and item["name"].lower().endswith(".md"):
            acc.append({"path": item["path"], "sha": item["sha"]})
        elif item["type"] == "dir":
            await _walk_tree(
                client,
                owner,
                repo,
                item["path"],
                max_depth,
                current_depth + 1,
                acc,
            )


async def fetch_blob(owner: str, repo: str, sha: str) -> str:
    """Fetch file content by blob SHA (handles files > 1 MB)."""
    async with _make_client() as client:
        resp = await _request_with_retry(client, "GET", f"/repos/{owner}/{repo}/git/blobs/{sha}")
        resp.raise_for_status()
        data = resp.json()
        return _decode_content(data)


def _decode_content(data: dict[str, str]) -> str:
    """Decode base64-encoded GitHub API content."""
    content = data.get("content", "")
    encoding = data.get("encoding", "base64")
    if encoding == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return content
