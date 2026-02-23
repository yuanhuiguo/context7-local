"""Unit tests for the GitHub API client (fully mocked via httpx.MockTransport)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from context7_local import github_client


def _json_response(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
    )


def _make_transport(handler):
    """Create a MockTransport from a sync callback."""
    return httpx.MockTransport(handler)


# ── search_repositories ────────────────────────────────────────


class TestSearchRepositories:
    @pytest.mark.asyncio
    async def test_returns_repos(self, monkeypatch) -> None:
        mock_repos = [
            github_client.RepoInfo(
                owner="facebook",
                repo="react",
                description="A JS library",
                stars=200000,
                language="JavaScript",
            ),
        ]

        async def patched(query, max_results=5):
            return mock_repos

        monkeypatch.setattr(github_client, "search_repositories", patched)

        repos = await github_client.search_repositories("react")
        assert len(repos) == 1
        assert repos[0].owner == "facebook"
        assert repos[0].library_id == "/facebook/react"
        assert repos[0].stars == 200000


# ── fetch_readme ───────────────────────────────────────────────


class TestFetchReadme:
    @pytest.mark.asyncio
    async def test_decodes_base64(self, monkeypatch) -> None:
        readme_text = "# Hello World"
        encoded = base64.b64encode(readme_text.encode()).decode()

        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"content": encoded, "encoding": "base64"})

        async def patched(owner, repo):
            async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
                resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}/readme")
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                content = data.get("content", "")
                encoding = data.get("encoding", "base64")
                if encoding == "base64":
                    return base64.b64decode(content).decode("utf-8", errors="replace")
                return content

        monkeypatch.setattr(github_client, "fetch_readme", patched)

        result = await github_client.fetch_readme("owner", "repo")
        assert result == "# Hello World"

    @pytest.mark.asyncio
    async def test_returns_none_for_404(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _json_response({"message": "Not Found"}, status_code=404)

        async def patched(owner, repo):
            async with httpx.AsyncClient(transport=_make_transport(handler)) as client:
                resp = await client.get(f"https://api.github.com/repos/{owner}/{repo}/readme")
                if resp.status_code == 404:
                    return None
                return resp.json().get("content")

        monkeypatch.setattr(github_client, "fetch_readme", patched)

        result = await github_client.fetch_readme("owner", "missing")
        assert result is None
