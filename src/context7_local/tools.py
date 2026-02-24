"""MCP tool implementations: resolve-library-id and query-docs.

Uses FastEmbed + Numpy for semantic vector ranking of document chunks.
"""

from __future__ import annotations

import logging

import httpx
import numpy as np

from context7_local import cache, chunker, embedder, github_client, scraper
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

    # Chunk all cached markdown
    all_chunks: list[chunker.Chunk] = []
    for path, content in docs.items():
        all_chunks.extend(chunker.chunk_markdown(content, source=path))

    if not all_chunks:
        return f"Documentation for {library_id} could not be chunked."

    # --- Semantic ranking ---
    ranked = _rank_chunks_semantic(query, owner, repo, all_chunks, top_k=5)

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
# Internal: semantic ranking (FastEmbed + Numpy)
# ---------------------------------------------------------------------------


def _chunk_id(chunk: chunker.Chunk) -> str:
    """Stable string identifier for a chunk used as matrix row index."""
    return f"{chunk.source}::{chunk.title}"


def _rank_chunks_semantic(
    query: str,
    owner: str,
    repo: str,
    chunks: list[chunker.Chunk],
    top_k: int = 5,
) -> list[chunker.Chunk]:
    """Rank chunks by cosine similarity to the query embedding.

    Strategy:
      1. Try to load a pre-built embedding matrix from the file cache.
      2. If the cache is stale / missing, regenerate embeddings for all chunks
         and persist them so subsequent queries are instant.
      3. Compute query embedding, then dot-product against the matrix
         (rows are L2-normalised, so dot == cosine similarity).
    """
    if not chunks:
        return []

    current_ids = [_chunk_id(c) for c in chunks]

    # Try to load persisted embeddings
    cached = cache.load_embeddings(owner, repo)
    if cached is not None:
        cached_ids, doc_matrix = cached
        if cached_ids == current_ids:
            log.debug("Embedding cache hit for %s/%s (%d chunks)", owner, repo, len(chunks))
        else:
            # Docs changed since last embed — regenerate
            log.info("Embedding cache stale for %s/%s, regenerating.", owner, repo)
            cached = None

    if cached is None:
        log.info("Generating embeddings for %d chunks (%s/%s)…", len(chunks), owner, repo)
        texts = [f"{c.title}\n{c.content}" for c in chunks]
        doc_matrix = embedder.embed_texts(texts)  # (N, D) float32, L2-normalised
        cache.save_embeddings(owner, repo, current_ids, doc_matrix)
        log.info("Embeddings persisted for %s/%s.", owner, repo)

    # Embed the query and compute cosine similarities via dot product
    q_vec = embedder.embed_query(query)  # (D,) unit vector
    scores: np.ndarray = doc_matrix @ q_vec  # (N,) cosine similarities

    # Pick top-k indices (stable argsort descending)
    top_indices = int(min(top_k, len(chunks)))
    ranked_idx = np.argsort(-scores)[:top_indices]

    return [chunks[int(i)] for i in ranked_idx]
