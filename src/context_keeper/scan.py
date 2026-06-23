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

FILE_TOOLS: dict[str, str] = {
    "AGENTS.md": "Kimi Code, OpenCode",
    "CLAUDE.md": "Claude Code",
    "CONTEXT.md": "project brief",
    "CONVENTIONS.md": "Aider / generic",
    ".cursorrules": "Cursor",
    ".aider.conf.yml": "Aider",
    ".github/copilot-instructions.md": "GitHub Copilot",
}


def tool_for(filename: str) -> str:
    """Return the tool name for a given context filename."""
    return FILE_TOOLS.get(filename, "")


IGNORED_DIRS = {
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


def _is_ignored(path: Path, root: Path) -> bool:
    """Check if path is inside a known-ignored directory."""
    for part in path.relative_to(root).parts:
        if part in IGNORED_DIRS:
            return True
    return False


def _should_prune_dir(name: str) -> bool:
    """Check if a directory should be pruned from traversal."""
    if name in IGNORED_DIRS:
        return True
    if name.startswith(".") and name != ".github":
        return True
    return False


def scan_directory(
    path: Path, config: Config | None = None, max_depth: int | None = None
) -> list[dict[str, Any]]:
    """Scan a directory for known context files."""
    results = []
    tracked_paths: dict[Path, tuple[str, str]] = {}

    if config:
        for project_name, project in config.projects.items():
            for file_name in project.resolve_files():
                tracked_paths[project.file_path(file_name)] = (project_name, file_name)

    start_depth = len(path.parts)

    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        current_depth = len(root_path.parts) - start_depth

        if max_depth is not None and current_depth > max_depth:
            dirs[:] = []
            continue

        if _is_ignored(root_path, path):
            dirs[:] = []
            continue

        dirs[:] = [d for d in dirs if not _should_prune_dir(d)]
        for file_name in files:
            file_path = root_path / file_name
            rel_path = str(file_path.relative_to(path))
            if (
                file_name not in KNOWN_CONTEXT_FILES
                and rel_path not in KNOWN_CONTEXT_FILES
            ):
                continue
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
