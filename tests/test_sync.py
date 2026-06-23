"""Tests for sync logic and FileStatus."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from context_keeper.config import Config
from context_keeper.markless import MarklessClient
from context_keeper.sync import FileStatus, MTIME_TOLERANCE_S, get_status


NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def make_status(
    local_mtime: datetime | None = None,
    remote_mtime: datetime | None = None,
    local_exists: bool = True,
    remote_exists: bool = True,
) -> FileStatus:
    return FileStatus(
        name="test.md",
        local_path=Path("/tmp/test.md"),
        local_mtime=local_mtime,
        remote_mtime=remote_mtime,
        local_exists=local_exists,
        remote_exists=remote_exists,
    )


class TestFileStatus:
    def test_local_only(self):
        s = make_status(local_exists=True, remote_exists=False)
        assert s.local_only is True
        assert s.remote_only is False

    def test_remote_only(self):
        s = make_status(local_exists=False, remote_exists=True)
        assert s.remote_only is True
        assert s.local_only is False

    def test_synced_within_tolerance(self):
        s = make_status(local_mtime=NOW, remote_mtime=NOW + timedelta(seconds=1))
        assert s.synced is True
        assert s.local_newer is False
        assert s.remote_newer is False

    def test_synced_exact_equal(self):
        s = make_status(local_mtime=NOW, remote_mtime=NOW)
        assert s.synced is True
        assert s.local_newer is False
        assert s.remote_newer is False

    def test_local_newer_beyond_tolerance(self):
        s = make_status(local_mtime=NOW, remote_mtime=NOW - timedelta(seconds=5))
        assert s.synced is False
        assert s.local_newer is True
        assert s.remote_newer is False

    def test_remote_newer_beyond_tolerance(self):
        s = make_status(local_mtime=NOW, remote_mtime=NOW + timedelta(seconds=5))
        assert s.synced is False
        assert s.local_newer is False
        assert s.remote_newer is True

    def test_boundary_at_tolerance(self):
        s = make_status(
            local_mtime=NOW, remote_mtime=NOW + timedelta(seconds=MTIME_TOLERANCE_S)
        )
        assert s.synced is False
        assert s.local_newer is False
        assert s.remote_newer is True

    def test_synced_barely_within_tolerance(self):
        s = make_status(
            local_mtime=NOW, remote_mtime=NOW + timedelta(seconds=MTIME_TOLERANCE_S - 1)
        )
        assert s.synced is True
        assert s.local_newer is False
        assert s.remote_newer is False

    def test_synced_false_when_missing_both(self):
        s = make_status(local_exists=False, remote_exists=False)
        assert s.synced is False
        assert s.local_newer is False
        assert s.remote_newer is False

    def test_synced_false_when_local_only(self):
        s = make_status(local_exists=True, remote_exists=False)
        assert s.synced is False

    def test_synced_false_when_remote_only(self):
        s = make_status(local_exists=False, remote_exists=True)
        assert s.synced is False

    def test_no_overlap_local_newer_and_synced(self):
        """Regression: local_newer and synced must be mutually exclusive."""
        for diff in range(-10, 11):
            s = make_status(local_mtime=NOW, remote_mtime=NOW + timedelta(seconds=diff))
            assert not (s.synced and s.local_newer), (
                f"diff={diff}: both synced and local_newer"
            )
            assert not (s.synced and s.remote_newer), (
                f"diff={diff}: both synced and remote_newer"
            )
            assert not (s.local_newer and s.remote_newer), (
                f"diff={diff}: both local_newer and remote_newer"
            )


class TestGetStatus:
    def test_returns_status_for_each_file(self, tmp_path: Path):
        config = Config(
            markless={"url": "", "username": "", "password": ""},
            projects={
                "demo": {
                    "local": str(tmp_path),
                    "remote": {"book": "B", "section": "S"},
                    "files": ["a.md", "b.md"],
                }
            },
        )
        project = config.projects["demo"]
        (tmp_path / "a.md").write_text("hello")
        client = MarklessClient(
            url="http://localhost:1", username="", password="", timeout=0.1
        )
        client._tree_cache = {"books": []}

        statuses = get_status(client, "demo", project)
        assert len(statuses) == 2
        assert statuses[0].name == "a.md"
        assert statuses[0].local_exists is True
        assert statuses[1].name == "b.md"
        assert statuses[1].local_exists is False
