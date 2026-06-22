"""Pull/push/status logic for context files."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config, ProjectConfig
from .markless import MarklessClient


class FileStatus:
    """Status of one context file."""

    def __init__(
        self,
        name: str,
        local_path: Path,
        local_mtime: datetime | None,
        remote_mtime: datetime | None,
        local_exists: bool,
        remote_exists: bool,
    ):
        self.name = name
        self.local_path = local_path
        self.local_mtime = local_mtime
        self.remote_mtime = remote_mtime
        self.local_exists = local_exists
        self.remote_exists = remote_exists

    @property
    def local_only(self) -> bool:
        return self.local_exists and not self.remote_exists

    @property
    def remote_only(self) -> bool:
        return self.remote_exists and not self.local_exists

    @property
    def synced(self) -> bool:
        if not (self.local_exists and self.remote_exists):
            return False
        if self.local_mtime is None or self.remote_mtime is None:
            return False
        # Allow 2-second tolerance for filesystem differences
        return abs((self.local_mtime - self.remote_mtime).total_seconds()) < 2

    @property
    def local_newer(self) -> bool:
        if not (self.local_exists and self.remote_exists):
            return False
        if self.local_mtime is None or self.remote_mtime is None:
            return False
        return self.local_mtime > self.remote_mtime

    @property
    def remote_newer(self) -> bool:
        if not (self.local_exists and self.remote_exists):
            return False
        if self.local_mtime is None or self.remote_mtime is None:
            return False
        return self.remote_mtime > self.local_mtime

    def __repr__(self) -> str:
        return f"<FileStatus {self.name}: local={self.local_exists} remote={self.remote_exists}>"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _backup(
    config: Config, project_name: str, file_name: str, path: Path
) -> Path | None:
    """Backup a file before overwriting it."""
    if not path.exists():
        return None
    ts = _utc_now().strftime("%Y%m%d-%H%M%S")
    backup_dir = config.backup_dir / project_name / file_name / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / file_name
    shutil.copy2(path, dest)
    return dest


def _local_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _touch_mtime(path: Path, mtime: datetime) -> None:
    """Set file mtime to match remote."""
    import os

    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def get_status(
    client: MarklessClient,
    project_name: str,
    project: ProjectConfig,
) -> list[FileStatus]:
    """Compare local and remote files for a project."""
    statuses = []
    for file_name in project.files:
        local_path = project.local / file_name
        local_exists = local_path.exists()
        local_mtime = _local_mtime(local_path) if local_exists else None
        remote_mtime = client.file_modified_at(
            project.remote.book, project.remote.section, file_name
        )
        remote_exists = remote_mtime is not None

        statuses.append(
            FileStatus(
                name=file_name,
                local_path=local_path,
                local_mtime=local_mtime,
                remote_mtime=remote_mtime,
                local_exists=local_exists,
                remote_exists=remote_exists,
            )
        )
    return statuses


def pull(
    client: MarklessClient,
    config: Config,
    project_name: str,
    project: ProjectConfig,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Download remote files to local project. Returns list of actions."""
    actions = []
    statuses = get_status(client, project_name, project)

    for status in statuses:
        if not status.remote_exists:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "not found on Markless",
                }
            )
            continue

        if status.local_exists and not force and status.local_newer:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "local is newer (use --force to overwrite)",
                }
            )
            continue

        # Backup before overwrite
        if status.local_exists:
            _backup(config, project_name, status.name, status.local_path)

        content = client.read_file(
            project.remote.book, project.remote.section, status.name
        )
        status.local_path.write_text(content, encoding="utf-8")
        if status.remote_mtime:
            _touch_mtime(status.local_path, status.remote_mtime)

        actions.append(
            {
                "file": status.name,
                "action": "pulled",
                "from": f"{project.remote.book}/{project.remote.section}",
            }
        )

    return actions


def push(
    client: MarklessClient,
    config: Config,
    project_name: str,
    project: ProjectConfig,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Upload local files to Markless. Returns list of actions."""
    actions = []
    statuses = get_status(client, project_name, project)

    for status in statuses:
        if not status.local_exists:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "not found locally",
                }
            )
            continue

        if status.remote_exists and not force and status.remote_newer:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "remote is newer (use --force to overwrite)",
                }
            )
            continue

        # Backup local before push
        _backup(config, project_name, status.name, status.local_path)

        content = status.local_path.read_text(encoding="utf-8")
        client.write_file(
            project.remote.book,
            project.remote.section,
            status.name,
            content,
        )

        # Match local mtime to remote so the next status shows synced.
        remote_mtime = client.file_modified_at(
            project.remote.book, project.remote.section, status.name
        )
        if remote_mtime:
            _touch_mtime(status.local_path, remote_mtime)

        actions.append(
            {
                "file": status.name,
                "action": "pushed",
                "to": f"{project.remote.book}/{project.remote.section}",
            }
        )

    return actions


def sync(
    client: MarklessClient,
    config: Config,
    project_name: str,
    project: ProjectConfig,
    strategy: str = "newest",
) -> list[dict[str, Any]]:
    """Bidirectional sync. strategy: newest | local | remote."""
    actions = []
    statuses = get_status(client, project_name, project)

    for status in statuses:
        if status.local_only or (status.local_exists and status.local_newer):
            if strategy == "remote":
                actions.append(
                    {
                        "file": status.name,
                        "action": "skipped",
                        "reason": "strategy=remote",
                    }
                )
                continue
            # Push local to remote
            _backup(config, project_name, status.name, status.local_path)
            content = status.local_path.read_text(encoding="utf-8")
            client.write_file(
                project.remote.book, project.remote.section, status.name, content
            )
            remote_mtime = client.file_modified_at(
                project.remote.book, project.remote.section, status.name
            )
            if remote_mtime:
                _touch_mtime(status.local_path, remote_mtime)
            actions.append(
                {
                    "file": status.name,
                    "action": "pushed",
                    "to": f"{project.remote.book}/{project.remote.section}",
                }
            )

        elif status.remote_only or (status.remote_exists and status.remote_newer):
            if strategy == "local":
                actions.append(
                    {
                        "file": status.name,
                        "action": "skipped",
                        "reason": "strategy=local",
                    }
                )
                continue
            # Pull remote to local
            if status.local_exists:
                _backup(config, project_name, status.name, status.local_path)
            content = client.read_file(
                project.remote.book, project.remote.section, status.name
            )
            status.local_path.write_text(content, encoding="utf-8")
            if status.remote_mtime:
                _touch_mtime(status.local_path, status.remote_mtime)
            actions.append(
                {
                    "file": status.name,
                    "action": "pulled",
                    "from": f"{project.remote.book}/{project.remote.section}",
                }
            )

        elif status.synced:
            actions.append({"file": status.name, "action": "unchanged"})

        elif not status.local_exists and not status.remote_exists:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "missing on both sides",
                }
            )

        else:
            actions.append(
                {
                    "file": status.name,
                    "action": "skipped",
                    "reason": "could not determine direction",
                }
            )

    return actions
