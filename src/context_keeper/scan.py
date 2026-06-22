"""Scan filesystem for AI context files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import Config


KNOWN_CONTEXT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".aider.conf.yml",
    ".github/copilot-instructions.md",
}


def _is_ignored(path: Path, root: Path) -> bool:
    """Check if path is inside common ignored directories."""
    ignored = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".buildozer",
        "bin",
        "obj",
        ".next",
    }
    for part in path.relative_to(root).parts:
        if part in ignored or part.startswith("."):
            return True
    return False


def scan_directory(path: Path, config: Config | None = None) -> list[dict[str, Any]]:
    """Scan a directory for known context files."""
    results = []
    tracked_paths: dict[Path, tuple[str, str]] = {}

    if config:
        for project_name, project in config.projects.items():
            for file_name in project.files:
                tracked_paths[project.local / file_name] = (project_name, file_name)

    for root, _dirs, files in os.walk(path):
        root_path = Path(root)
        if _is_ignored(root_path, path):
            continue
        for file_name in files:
            if file_name not in KNOWN_CONTEXT_FILES:
                continue
            file_path = root_path / file_name
            if _is_ignored(file_path, path):
                continue
            if file_path in tracked_paths:
                project_name, tracked_name = tracked_paths[file_path]
                status = f"tracked ({project_name})"
            else:
                status = "untracked"
            results.append(
                {
                    "path": file_path,
                    "name": file_name,
                    "status": status,
                }
            )

    return sorted(results, key=lambda x: str(x["path"]))
