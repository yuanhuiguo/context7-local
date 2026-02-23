"""Async website documentation scraper with HTML→Markdown conversion.

Crawls documentation websites (e.g. fastapi.tiangolo.com) via BFS,
extracts clean text from HTML, and returns docs ready for caching.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

log = logging.getLogger("context7-local")

_STRIP_TAGS = {"nav", "header", "footer", "script", "style", "aside", "svg", "form"}
_MAX_PAGE_CHARS = 200_000  # skip absurdly large pages
_REQUEST_TIMEOUT = 15.0


async def scrape_docs_site(
    base_url: str,
    max_pages: int = 30,
    max_depth: int = 2,
) -> dict[str, str]:
    """Crawl a docs site starting from *base_url*.

    Returns a dict mapping ``{sanitized_path}.md`` to extracted Markdown text.
    Only follows internal links within the same domain.

    Args:
        base_url: Root URL of the documentation site.
        max_pages: Maximum number of pages to fetch.
        max_depth: Maximum link-follow depth from the root.
    """
    parsed_base = urlparse(base_url)
    domain = parsed_base.netloc
    if not domain:
        log.warning("scrape_docs_site: invalid base_url %s", base_url)
        return {}

    visited: set[str] = set()
    results: dict[str, str] = {}
    # BFS queue: (url, depth)
    queue: list[tuple[str, int]] = [(base_url, 0)]

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "context7-local/0.1"},
    ) as client:
        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            normalized = _normalize_url(url)
            if normalized in visited:
                continue
            visited.add(normalized)

            try:
                resp = await client.get(url)
            except (httpx.HTTPError, OSError) as exc:
                log.debug("scrape skip %s: %s (%s)", url, type(exc).__name__, exc)
                continue

            if resp.status_code != 200:
                continue

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                continue

            html = resp.text
            if len(html) > _MAX_PAGE_CHARS:
                log.debug("Skip %s: too large (%d > %d)", url, len(html), _MAX_PAGE_CHARS)
                continue

            text = _html_to_markdown(html)
            if not text or len(text.strip()) < 50:
                log.debug("Skip %s: text too short (%d)", url, len(text.strip()) if text else 0)
                continue

            rel_path = _url_to_path(url, domain)
            results[rel_path] = text
            log.info("Scraped %s -> %s (%d chars)", url, rel_path, len(text))

            # Discover links for BFS (only if within depth budget)
            if depth < max_depth:
                for link in _extract_links(html, url, domain):
                    if _normalize_url(link) not in visited:
                        queue.append((link, depth + 1))

    log.info("scraped %d pages from %s", len(results), domain)
    return results


def _html_to_markdown(html: str) -> str:
    """Extract clean text from HTML, preserving code blocks as fenced Markdown."""
    soup = BeautifulSoup(html, "lxml")

    # Remove unwanted elements
    for tag_name in _STRIP_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Convert <pre>/<code> blocks to fenced code
    for pre in soup.find_all("pre"):
        code_el = pre.find("code")
        source = code_el if code_el else pre
        code_text = source.get_text()
        # Detect language from class (e.g. class="language-python")
        lang = _detect_lang(source)
        pre.replace_with(f"\n```{lang}\n{code_text}\n```\n")

    # Extract text
    text = soup.get_text(separator="\n")

    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_lang(el: Tag | str) -> str:
    """Try to extract language hint from a code/pre element's class."""
    if isinstance(el, str):
        return ""
    classes = el.get("class", [])
    if isinstance(classes, list):
        for cls in classes:
            if isinstance(cls, str) and cls.startswith("language-"):
                return cls.removeprefix("language-")
    return ""


def _extract_links(html: str, page_url: str, domain: str) -> list[str]:
    """Extract same-domain links from HTML."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if isinstance(href, list):
            href = href[0]
        # Skip anchors, mailto, javascript
        if href.startswith(("#", "mailto:", "javascript:")):
            continue
        abs_url = urljoin(page_url, href)
        parsed = urlparse(abs_url)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            # Strip fragment
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            links.append(clean)
    return links


def _normalize_url(url: str) -> str:
    """Normalize URL for deduplication (strip trailing slash and fragment)."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.netloc}{path}"


def _url_to_path(url: str, domain: str) -> str:
    """Convert a URL to a cache-friendly relative path ending in .md."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "index"
    # Sanitize
    path = re.sub(r"[^a-zA-Z0-9_/.-]", "_", path)
    # Remove existing extension and add .md
    if path.endswith((".html", ".htm")):
        path = path.rsplit(".", 1)[0]
    return f"{path}.md"
