"""MCP tool implementations: resolve-library-id and query-docs.

Uses a lightweight TF-IDF scorer for document chunk ranking.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter

import httpx

from context7_local import cache, chunker, github_client, scraper
from context7_local.server import mcp

log = logging.getLogger("context7-local")

# ---------------------------------------------------------------------------
# Tool 1: resolve-library-id
# ---------------------------------------------------------------------------


@mcp.tool(name="resolve-library-id")
async def resolve_library_id(library_name: str) -> str:
    """Search for a library on GitHub and return matching library IDs.

    Args:
        library_name: The library or package name to search for.

    Returns:
        Formatted text listing matching libraries with IDs, descriptions,
        stars, and primary language.
    """
    try:
        repos = await github_client.search_repositories(library_name, max_results=5)
    except (httpx.HTTPError, OSError) as exc:
        log.error("search_repositories failed: %s", exc)
        return (
            f"Failed to search GitHub for '{library_name}': "
            f"{type(exc).__name__}. Check network or set GITHUB_TOKEN."
        )

    if not repos:
        return f"No repositories found for '{library_name}'."

    lines: list[str] = []
    for r in repos:
        lines.append(
            f"- **{r.library_id}** — "
            f"{r.description or '(no description)'}\n"
            f"  Stars: {r.stars:,} | Language: {r.language}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: query-docs
# ---------------------------------------------------------------------------


@mcp.tool(name="query-docs")
async def query_docs(library_id: str, query: str) -> str:
    """Fetch documentation for a library and return relevant snippets.

    Args:
        library_id: Library identifier in /{owner}/{repo} format.
        query: The question or topic to search for in the documentation.

    Returns:
        Top-matching documentation chunks, concatenated as text.
    """
    parts = library_id.strip("/").split("/")
    if len(parts) != 2:
        return f"Invalid library_id format: '{library_id}'. Expected /{{owner}}/{{repo}}"

    owner, repo = parts

    # Ensure docs are cached
    if not cache.is_cached(owner, repo):
        try:
            await _fetch_and_cache(owner, repo)
        except (httpx.HTTPError, OSError) as exc:
            log.error("fetch_and_cache failed for %s/%s: %s", owner, repo, exc)
            return (
                f"Failed to fetch documentation for {library_id}: "
                f"{type(exc).__name__}. Check network or set GITHUB_TOKEN."
            )

    # Load cached docs
    docs = cache.load_all_docs(owner, repo)
    if not docs:
        return f"No documentation found for {library_id}."

    # Chunk and rank
    all_chunks: list[chunker.Chunk] = []
    for path, content in docs.items():
        all_chunks.extend(chunker.chunk_markdown(content, source=path))

    if not all_chunks:
        return f"Documentation for {library_id} could not be chunked."

    ranked = _rank_chunks(query, all_chunks, top_k=5)

    # Format output
    sections: list[str] = []
    for chunk in ranked:
        sections.append(f"### {chunk.title}\nSource: {chunk.source}\n\n{chunk.content}")
    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Internal: fetch docs from GitHub and write to cache
# ---------------------------------------------------------------------------


async def _fetch_and_cache(owner: str, repo: str) -> None:
    """Fetch README + docs/ directory + official website and persist to cache.

    Network errors are caught per-stage so a partial fetch (e.g. README
    succeeds but /docs times out) still caches whatever was retrieved.
    """
    # Stage 1: README
    try:
        readme = await github_client.fetch_readme(owner, repo)
        if readme:
            cache.save_doc(owner, repo, "readme.md", readme)
    except (httpx.HTTPError, OSError) as exc:
        log.warning("Failed to fetch README for %s/%s: %s", owner, repo, exc)

    # Stage 2: docs/ directory tree
    try:
        doc_files = await github_client.list_docs_directory(owner, repo, path="docs")
        for entry in doc_files:
            try:
                content = await github_client.fetch_blob(owner, repo, entry["sha"])
                cache.save_doc(owner, repo, entry["path"], content)
            except (httpx.HTTPError, OSError) as exc:
                log.warning("Failed to fetch blob %s: %s", entry["path"], exc)
    except (httpx.HTTPError, OSError) as exc:
        log.warning("Failed to list docs/ for %s/%s: %s", owner, repo, exc)

    # Stage 3: Official documentation website
    try:
        homepage = await github_client.fetch_homepage_url(owner, repo)
        if homepage and _is_docs_url(homepage):
            scraped = await scraper.scrape_docs_site(homepage)
            for path, content in scraped.items():
                cache.save_doc(owner, repo, f"web/{path}", content)
    except (httpx.HTTPError, OSError) as exc:
        log.warning("Failed to scrape website for %s/%s: %s", owner, repo, exc)

    cache.mark_fetched(owner, repo)


# ---------------------------------------------------------------------------
# Internal: URL filtering for website scraping
# ---------------------------------------------------------------------------

_SKIP_DOMAINS = {
    "github.com",
    "gitlab.com",
    "npmjs.com",
    "www.npmjs.com",
    "pypi.org",
    "rubygems.org",
    "crates.io",
    "pkg.go.dev",
    "hub.docker.com",
}


def _is_docs_url(url: str) -> bool:
    """Return True if the URL looks like a documentation site worth scraping.

    Filters out package registries and source code hosting that we already
    handle via the GitHub API.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return bool(domain) and domain not in _SKIP_DOMAINS


# ---------------------------------------------------------------------------
# Internal: lightweight TF-IDF ranking
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def _rank_chunks(query: str, chunks: list[chunker.Chunk], top_k: int = 5) -> list[chunker.Chunk]:
    """Rank *chunks* by TF-IDF similarity to *query*."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return chunks[:top_k]

    # Build document frequencies
    n = len(chunks)
    doc_freq: Counter[str] = Counter()
    chunk_tokens: list[list[str]] = []
    for chunk in chunks:
        tokens = _tokenize(f"{chunk.title} {chunk.content}")
        chunk_tokens.append(tokens)
        unique = set(tokens)
        for t in unique:
            doc_freq[t] += 1

    # Score each chunk
    scored: list[tuple[float, int]] = []
    for idx, tokens in enumerate(chunk_tokens):
        tf = Counter(tokens)
        total = len(tokens) or 1
        score = 0.0
        for qt in query_tokens:
            if qt in tf:
                tf_val = tf[qt] / total
                idf_val = math.log((n + 1) / (doc_freq.get(qt, 0) + 1)) + 1
                score += tf_val * idf_val
        scored.append((score, idx))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunks[idx] for _, idx in scored[:top_k]]
