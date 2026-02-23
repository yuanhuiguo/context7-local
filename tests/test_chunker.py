"""Unit tests for the Markdown chunker."""

from context7_local.chunker import chunk_markdown


class TestChunkMarkdown:
    def test_splits_on_h1(self) -> None:
        md = "# Title A\nHello\n# Title B\nWorld"
        chunks = chunk_markdown(md, source="test.md")
        assert len(chunks) == 2
        assert chunks[0].title == "Title A"
        assert "Hello" in chunks[0].content
        assert chunks[1].title == "Title B"
        assert "World" in chunks[1].content

    def test_splits_on_h2(self) -> None:
        md = "## First\nAAA\n## Second\nBBB"
        chunks = chunk_markdown(md, source="f.md")
        assert len(chunks) == 2

    def test_preserves_code_blocks(self) -> None:
        md = (
            "# Header\nSome text\n```python\n# This is code, not heading\n"
            "def foo():\n    pass\n```\nMore text"
        )
        chunks = chunk_markdown(md, source="f.md")
        assert len(chunks) == 1
        assert "# This is code, not heading" in chunks[0].content

    def test_truncates_long_chunks(self) -> None:
        long_content = "x" * 5000
        md = f"# Big\n{long_content}"
        chunks = chunk_markdown(md, source="f.md")
        assert len(chunks) == 1
        assert len(chunks[0].content) < 2200  # ~2000 + truncation marker

    def test_default_title_when_no_heading(self) -> None:
        md = "Just some plain text without any heading."
        chunks = chunk_markdown(md, source="readme.md")
        assert len(chunks) == 1
        assert chunks[0].title == "readme.md"
        assert "plain text" in chunks[0].content

    def test_empty_input(self) -> None:
        chunks = chunk_markdown("", source="empty.md")
        assert chunks == []
