"""Pull/push/status logic for context files."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config, ProjectConfig
from .markless import MarklessClient

MTIME_TOLERANCE_S = 2


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
        return (
            abs((self.local_mtime - self.remote_mtime).total_seconds())
            < MTIME_TOLERANCE_S
        )

    @property
    def local_newer(self) -> bool:
        if not (self.local_exists and self.remote_exists):
            return False
        if self.local_mtime is None or self.remote_mtime is None:
            return False
        return (
            self.local_mtime - self.remote_mtime
        ).total_seconds() >= MTIME_TOLERANCE_S

    @property
    def remote_newer(self) -> bool:
        if not (self.local_exists and self.remote_exists):
            return False
        if self.local_mtime is None or self.remote_mtime is None:
            return False
        return (
            self.remote_mtime - self.local_mtime
        ).total_seconds() >= MTIME_TOLERANCE_S

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
    safe_name = file_name.replace("/", "_").replace("\\", "_")
    backup_dir = config.backup_dir / project_name / safe_name / ts
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / path.name
    shutil.copy2(path, dest)
    return dest


def _local_mtime(path: Path) -> datetime | None:
    if not path.exists():
        return None
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _touch_mtime(path: Path, mtime: datetime) -> None:
    """Set file mtime to match remote."""
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def _mirror(project: ProjectConfig, file_name: str) -> None:
    """Copy a pulled file to the mirror directory if configured."""
    if not project.mirror:
        return
    src = project.file_path(file_name)
    if not src.exists():
        return
    if project.dir is not None:
        dst = project.mirror / file_name.replace("_", "/")
    else:
        dst = project.mirror / file_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _local_path(project: ProjectConfig, file_name: str) -> Path:
    """Resolve a file name to its local path, handling dir-based projects."""
    if project.dir is not None:
        return project.local / file_name.replace("_", "/")
    return project.local / file_name


def get_status(
    client: MarklessClient,
    project_name: str,
    project: ProjectConfig,
) -> list[FileStatus]:
    """Compare local and remote files for a project.

    Filenames are matched case-insensitively so that cross-platform sync
    (e.g. Windows vs Linux) does not show spurious conflicts for files that
    differ only in case.
    """
    local_files = {name: project.file_path(name) for name in project.resolve_files()}
    remote_files = {
        f["name"]: f
        for f in client.list_files(
            book=project.remote.book, section=project.remote.section
        )
    }

    # Build case-insensitive index. Prefer the local filename as the canonical
    # name so the displayed name matches the local filesystem.
    canonical: dict[str, str] = {}
    for name in local_files:
        canonical[name.lower()] = name
    for name in remote_files:
        canonical.setdefault(name.lower(), name)

    statuses = []
    for key in sorted(canonical):
        file_name = canonical[key]
        local_path = local_files.get(file_name)
        if local_path is None:
            local_path = project.file_path(file_name)
        local_exists = local_path.exists()
        local_mtime = _local_mtime(local_path) if local_exists else None

        remote_info = remote_files.get(file_name)
        if remote_info is None:
            # Fall back to case-insensitive remote lookup.
            remote_info = remote_files.get(key)
        if remote_info is not None:
            remote_mtime = datetime.fromisoformat(remote_info["modifiedAt"])
            remote_exists = True
        else:
            remote_mtime = None
            remote_exists = False

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
        status.local_path.parent.mkdir(parents=True, exist_ok=True)
        status.local_path.write_text(content, encoding="utf-8")
        if status.remote_mtime:
            _touch_mtime(status.local_path, status.remote_mtime)
        _mirror(project, status.name)

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
            status.local_path.parent.mkdir(parents=True, exist_ok=True)
            status.local_path.write_text(content, encoding="utf-8")
            if status.remote_mtime:
                _touch_mtime(status.local_path, status.remote_mtime)
            _mirror(project, status.name)
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


def delete_files(
    client: MarklessClient,
    config: Config,
    project_name: str,
    project: ProjectConfig,
    files: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Delete files from Markless. If files is None, deletes all remote files."""
    actions = []
    remote = client.list_files(book=project.remote.book, section=project.remote.section)
    for f in remote:
        name = f["name"]
        if files is not None and name.lower() not in {x.lower() for x in files}:
            continue
        client.delete_file(project.remote.book, project.remote.section, name)
        actions.append({"file": name, "action": "deleted"})
    return actions
