"""Tests for the Markless HTTP client."""

from datetime import datetime, timezone

from context_keeper.markless import MarklessClient


class TestUrlConstruction:
    def test_url_join_strips_trailing_slash(self):
        client = MarklessClient(url="http://example.com/", username="u", password="p")
        assert client._url("/health") == "http://example.com/health"

    def test_url_join_no_trailing_slash(self):
        client = MarklessClient(url="http://example.com", username="u", password="p")
        assert client._url("/health") == "http://example.com/health"

    def test_url_join_subpath(self):
        client = MarklessClient(
            url="http://example.com/api", username="u", password="p"
        )
        assert client._url("/health") == "http://example.com/api/health"


class TestCacheInvalidation:
    def test_cache_initially_none(self):
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        assert client._tree_cache is None

    def test_invalidate_cache_clears(self):
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        client._tree_cache = {"books": []}
        client.invalidate_cache()
        assert client._tree_cache is None

    def test_tree_returns_cached(self):
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        client._tree_cache = {"books": []}
        assert client.tree() == {"books": []}


class TestFileModifiedAt:
    def test_handles_z_suffix(self):
        dt = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        client._tree_cache = {
            "books": [
                {
                    "name": "Context",
                    "sections": [
                        {
                            "name": "demo",
                            "files": [
                                {
                                    "name": "AGENTS.md",
                                    "size": 100,
                                    "modifiedAt": "2026-06-22T12:00:00Z",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        result = client.file_modified_at("Context", "demo", "AGENTS.md")
        assert result == dt

    def test_returns_none_for_missing_file(self):
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        client._tree_cache = {"books": []}
        result = client.file_modified_at("Context", "demo", "nonexistent.md")
        assert result is None
