"""Show differences between local and remote context files."""

from __future__ import annotations

import difflib
from typing import Any

from .config import ProjectConfig
from .markless import MarklessClient
from .sync import get_status


def diff_project(
    client: MarklessClient,
    project_name: str,
    project: ProjectConfig,
) -> list[dict[str, Any]]:
    """Return diff info for each file in the project."""
    results = []
    statuses = get_status(client, project_name, project)

    for status in statuses:
        if not status.local_exists or not status.remote_exists:
            results.append(
                {
                    "file": status.name,
                    "local_exists": status.local_exists,
                    "remote_exists": status.remote_exists,
                    "diff": None,
                }
            )
            continue

        local_content = status.local_path.read_text(encoding="utf-8").splitlines()
        remote_content = client.read_file(
            project.remote.book, project.remote.section, status.name
        ).splitlines()

        diff = list(
            difflib.unified_diff(
                remote_content,
                local_content,
                fromfile=f"remote/{status.name}",
                tofile=f"local/{status.name}",
                lineterm="",
            )
        )

        results.append(
            {
                "file": status.name,
                "local_exists": True,
                "remote_exists": True,
                "diff": "\n".join(diff) if diff else None,
            }
        )

    return results
