"""Unit tests for the website documentation scraper."""

from __future__ import annotations

import pytest

from context7_local.scraper import (
    _detect_lang,
    _extract_links,
    _html_to_markdown,
    _normalize_url,
    _url_to_path,
    scrape_docs_site,
)

# ---------------------------------------------------------------------------
# _html_to_markdown
# ---------------------------------------------------------------------------


class TestHtmlToMarkdown:
    def test_basic_text(self) -> None:
        html = "<html><body><p>Hello world</p></body></html>"
        result = _html_to_markdown(html)
        assert "Hello world" in result

    def test_strips_nav_and_footer(self) -> None:
        html = """
        <html><body>
            <nav>Menu items</nav>
            <main><p>Content here</p></main>
            <footer>Footer stuff</footer>
        </body></html>
        """
        result = _html_to_markdown(html)
        assert "Content here" in result
        assert "Menu items" not in result
        assert "Footer stuff" not in result

    def test_strips_script_and_style(self) -> None:
        html = """
        <html><body>
            <style>.foo { color: red; }</style>
            <script>alert('x')</script>
            <p>Visible</p>
        </body></html>
        """
        result = _html_to_markdown(html)
        assert "Visible" in result
        assert "alert" not in result
        assert "color" not in result

    def test_preserves_code_blocks(self) -> None:
        html = """
        <html><body>
            <p>Example:</p>
            <pre><code class="language-python">print("hello")</code></pre>
        </body></html>
        """
        result = _html_to_markdown(html)
        assert "```python" in result
        assert 'print("hello")' in result

    def test_code_block_without_language(self) -> None:
        html = "<html><body><pre><code>foo = 1</code></pre></body></html>"
        result = _html_to_markdown(html)
        assert "```\n" in result
        assert "foo = 1" in result


# ---------------------------------------------------------------------------
# _detect_lang
# ---------------------------------------------------------------------------


class TestDetectLang:
    def test_with_language_class(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup('<code class="language-javascript">x</code>', "lxml")
        code = soup.find("code")
        assert _detect_lang(code) == "javascript"

    def test_without_class(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<code>x</code>", "lxml")
        code = soup.find("code")
        assert _detect_lang(code) == ""

    def test_string_input(self) -> None:
        assert _detect_lang("not a tag") == ""


# ---------------------------------------------------------------------------
# _extract_links
# ---------------------------------------------------------------------------


class TestExtractLinks:
    def test_extracts_same_domain_links(self) -> None:
        html = '<html><body><a href="/docs/guide">Guide</a></body></html>'
        links = _extract_links(html, "https://example.com/", "example.com")
        assert "https://example.com/docs/guide" in links

    def test_ignores_external_links(self) -> None:
        html = '<html><body><a href="https://other.com/page">X</a></body></html>'
        links = _extract_links(html, "https://example.com/", "example.com")
        assert len(links) == 0

    def test_ignores_anchors_and_mailto(self) -> None:
        html = """
        <html><body>
            <a href="#section">Anchor</a>
            <a href="mailto:x@y.com">Email</a>
            <a href="javascript:void(0)">JS</a>
        </body></html>
        """
        links = _extract_links(html, "https://example.com/", "example.com")
        assert len(links) == 0


# ---------------------------------------------------------------------------
# _normalize_url / _url_to_path
# ---------------------------------------------------------------------------


class TestUrlHelpers:
    def test_normalize_strips_trailing_slash(self) -> None:
        assert _normalize_url("https://example.com/docs/") == "example.com/docs"

    def test_normalize_root(self) -> None:
        assert _normalize_url("https://example.com/") == "example.com/"

    def test_url_to_path_basic(self) -> None:
        result = _url_to_path("https://example.com/docs/guide", "example.com")
        assert result == "docs/guide.md"

    def test_url_to_path_root(self) -> None:
        result = _url_to_path("https://example.com/", "example.com")
        assert result == "index.md"

    def test_url_to_path_strips_html(self) -> None:
        result = _url_to_path("https://example.com/page.html", "example.com")
        assert result == "page.md"


# ---------------------------------------------------------------------------
# _is_docs_url (imported from tools but tested here for convenience)
# ---------------------------------------------------------------------------


class TestIsDocsUrl:
    def test_docs_site(self) -> None:
        from context7_local.tools import _is_docs_url

        assert _is_docs_url("https://fastapi.tiangolo.com") is True

    def test_github(self) -> None:
        from context7_local.tools import _is_docs_url

        assert _is_docs_url("https://github.com/fastapi/fastapi") is False

    def test_pypi(self) -> None:
        from context7_local.tools import _is_docs_url

        assert _is_docs_url("https://pypi.org/project/fastapi/") is False

    def test_npmjs(self) -> None:
        from context7_local.tools import _is_docs_url

        assert _is_docs_url("https://www.npmjs.com/package/react") is False

    def test_empty(self) -> None:
        from context7_local.tools import _is_docs_url

        assert _is_docs_url("") is False


# ---------------------------------------------------------------------------
# scrape_docs_site (mocked HTTP)
# ---------------------------------------------------------------------------


class TestScrapDocsSite:
    @pytest.mark.asyncio
    async def test_scrapes_single_page(self) -> None:
        """Verify scraper fetches and converts a single page."""
        from unittest.mock import patch

        import httpx

        page_html = """
        <html><body>
            <h1>Getting Started</h1>
            <p>Welcome to our documentation portal with enough content here.</p>
        </body></html>
        """

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                text=page_html,
                headers={"content-type": "text/html"},
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

        with patch("context7_local.scraper.httpx.AsyncClient", return_value=mock_client):
            result = await scrape_docs_site("https://docs.example.com", max_pages=1)

        assert len(result) >= 1
        content = list(result.values())[0]
        assert "Getting Started" in content
        assert "Welcome to our documentation" in content

    @pytest.mark.asyncio
    async def test_invalid_url_returns_empty(self) -> None:
        """Invalid base URL should return empty dict."""
        result = await scrape_docs_site("not-a-url")
        assert result == {}
