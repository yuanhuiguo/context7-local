"""Unit tests for MCP tools (resolve-library-id, query-docs)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from context7_local import cache, chunker, github_client
from context7_local.tools import _rank_chunks, query_docs, resolve_library_id


class TestResolveLibraryId:
    @pytest.mark.asyncio
    async def test_formats_results(self) -> None:
        mock_repos = [
            github_client.RepoInfo(
                owner="facebook",
                repo="react",
                description="A JS library",
                stars=200000,
                language="JavaScript",
            ),
        ]
        with patch.object(
            github_client, "search_repositories", new_callable=AsyncMock, return_value=mock_repos
        ):
            result = await resolve_library_id("react")
            assert "/facebook/react" in result
            assert "200,000" in result

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        with patch.object(
            github_client, "search_repositories", new_callable=AsyncMock, return_value=[]
        ):
            result = await resolve_library_id("nonexistent_xyz_lib")
            assert "No repositories found" in result


class TestQueryDocs:
    @pytest.mark.asyncio
    async def test_invalid_library_id(self) -> None:
        result = await query_docs("invalid-format", "anything")
        assert "Invalid library_id" in result

    @pytest.mark.asyncio
    async def test_returns_ranked_chunks(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        # Pre-populate cache
        doc = "# Setup\nHow to install\n## Usage\nHow to use the API"
        cache.save_doc("owner", "repo", "readme.md", doc)
        cache.mark_fetched("owner", "repo")

        result = await query_docs("/owner/repo", "install setup")
        assert "Setup" in result or "install" in result.lower()

    @pytest.mark.asyncio
    async def test_fetches_when_not_cached(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CACHE_DIR", str(tmp_path))

        with (
            patch.object(
                github_client,
                "fetch_readme",
                new_callable=AsyncMock,
                return_value="# README\nHello",
            ),
            patch.object(
                github_client, "list_docs_directory", new_callable=AsyncMock, return_value=[]
            ),
        ):
            result = await query_docs("/owner/repo", "hello")
            assert "Hello" in result


class TestRankChunks:
    def test_ranks_by_relevance(self) -> None:
        chunks = [
            chunker.Chunk(title="Install", content="pip install foo bar", source="a.md"),
            chunker.Chunk(title="Unrelated", content="nothing here about install", source="b.md"),
            chunker.Chunk(title="Setup", content="install install install setup", source="c.md"),
        ]
        ranked = _rank_chunks("install", chunks, top_k=2)
        assert len(ranked) == 2
        # The chunk with more "install" mentions should rank higher
        assert ranked[0].title == "Setup"

    def test_empty_query(self) -> None:
        chunks = [
            chunker.Chunk(title="A", content="Content", source="a.md"),
        ]
        ranked = _rank_chunks("", chunks, top_k=5)
        assert len(ranked) == 1
