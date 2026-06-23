"""Markless HTTP API client."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx


class MarklessClient:
    """Thin client for the Markless library REST API."""

    def __init__(self, url: str, username: str, password: str, timeout: float = 30.0):
        self.base_url = url.rstrip("/") + "/"
        self.auth = (username, password) if username and password else None
        self.timeout = timeout
        self.client = httpx.Client(
            auth=self.auth, timeout=timeout, follow_redirects=True
        )
        self._tree_cache: dict[str, Any] | None = None

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def health(self) -> dict[str, Any]:
        """Check Markless health."""
        r = self.client.get(self._url("/health"))
        r.raise_for_status()
        return r.json()

    def tree(self) -> dict[str, Any]:
        """Return the full library tree (cached)."""
        if self._tree_cache is not None:
            return self._tree_cache
        r = self.client.get(self._url("/api/library/tree"))
        r.raise_for_status()
        self._tree_cache = r.json()
        return self._tree_cache

    def invalidate_cache(self) -> None:
        """Clear the cached tree (call after writes)."""
        self._tree_cache = None

    def read_file(self, book: str, section: str, file: str) -> str:
        """Read a markdown file from Markless."""
        params = {"book": book, "section": section, "file": file}
        r = self.client.get(self._url("/api/library/file"), params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("content", "")

    def write_file(
        self, book: str, section: str, file: str, content: str
    ) -> dict[str, Any]:
        """Write a markdown file to Markless.

        Uses /api/library/sync because /api/library/export does not create
        parent directories for new books/sections.
        """
        payload = {
            "books": [
                {
                    "name": book,
                    "sections": [
                        {
                            "name": section,
                            "files": [
                                {"name": file, "content": content},
                            ],
                        }
                    ],
                }
            ]
        }
        r = self.client.post(self._url("/api/library/sync"), json=payload)
        r.raise_for_status()
        self._tree_cache = None
        return r.json()

    def list_files(
        self, book: str | None = None, section: str | None = None
    ) -> list[dict[str, Any]]:
        """List files in the library, optionally filtered by book/section."""
        tree = self.tree()
        files = []
        for b in tree.get("books", []):
            if book and b["name"] != book:
                continue
            for s in b.get("sections", []):
                if section and s["name"] != section:
                    continue
                for f in s.get("files", []):
                    files.append(
                        {
                            "book": b["name"],
                            "section": s["name"],
                            "name": f["name"],
                            "size": f["size"],
                            "modifiedAt": f["modifiedAt"],
                        }
                    )
        return files

    def file_modified_at(self, book: str, section: str, file: str) -> datetime | None:
        """Get remote file modification time, or None if not present."""
        files = self.list_files(book=book, section=section)
        for f in files:
            if f["name"].lower() == file.lower():
                return datetime.fromisoformat(f["modifiedAt"])
        return None

    def delete_file(self, book: str, section: str, file: str) -> dict[str, Any]:
        """Delete a file from Markless by syncing the section without it."""
        tree = self.tree()
        payload: dict[str, Any] = {"books": []}
        for b in tree.get("books", []):
            if b["name"] != book:
                continue
            sections = []
            for s in b.get("sections", []):
                if s["name"] != section:
                    continue
                kept_files = []
                for f in s.get("files", []):
                    if f["name"].lower() == file.lower():
                        continue
                    content = self.read_file(book, section, f["name"])
                    kept_files.append({"name": f["name"], "content": content})
                sections.append({"name": section, "files": kept_files})
            payload["books"].append({"name": book, "sections": sections})
        r = self.client.post(self._url("/api/library/sync"), json=payload)
        r.raise_for_status()
        self._tree_cache = None
        return r.json()

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> MarklessClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
