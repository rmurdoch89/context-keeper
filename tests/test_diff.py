"""Tests for diff functionality."""

from pathlib import Path

from context_keeper.config import Config
from context_keeper.diff import diff_project
from context_keeper.markless import MarklessClient


def test_diff_local_only(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("local content")
    config = Config(
        markless={"url": "", "username": "", "password": ""},
        projects={
            "demo": {
                "local": str(tmp_path),
                "remote": {"book": "B", "section": "S"},
                "files": ["AGENTS.md"],
            }
        },
    )
    project = config.projects["demo"]
    client = MarklessClient(
        url="http://localhost:1", username="", password="", timeout=0.1
    )
    client._tree_cache = {"books": []}

    results = diff_project(client, "demo", project)
    assert len(results) == 1
    assert results[0]["file"] == "AGENTS.md"
    assert results[0]["local_exists"] is True
    assert results[0]["remote_exists"] is False
    assert results[0]["diff"] is None


def test_diff_missing_both(tmp_path: Path):
    config = Config(
        markless={"url": "", "username": "", "password": ""},
        projects={
            "demo": {
                "local": str(tmp_path),
                "remote": {"book": "B", "section": "S"},
                "files": ["missing.md"],
            }
        },
    )
    project = config.projects["demo"]
    client = MarklessClient(
        url="http://localhost:1", username="", password="", timeout=0.1
    )
    client._tree_cache = {"books": []}

    results = diff_project(client, "demo", project)
    assert results[0]["local_exists"] is False
    assert results[0]["remote_exists"] is False
