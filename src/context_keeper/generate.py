"""Generate CONTEXT.md from repository metadata."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_TODOS = 20
MAX_COMMITS = 10
MAX_README_LINES = 80


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _git_remote(cwd: Path) -> str:
    return _run(["git", "remote", "get-url", "origin"], cwd)


def _git_recent_commits(cwd: Path, limit: int = MAX_COMMITS) -> list[str]:
    out = _run(
        ["git", "log", f"--max-count={limit}", "--pretty=format:%h %s"],
        cwd,
    )
    if not out:
        return []
    return out.splitlines()


def _git_branch(cwd: Path) -> str:
    return _run(["git", "branch", "--show-current"], cwd)


def _find_todos(cwd: Path, limit: int = MAX_TODOS) -> list[str]:
    """Find TODO/FIXME/HACK comments in code files."""
    todos = []
    pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)\s*:?\s*(.+)", re.IGNORECASE)
    # Common code file extensions; skip node_modules, .venv, etc.
    for ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".md"):
        for path in cwd.rglob(f"*{ext}"):
            if any(
                part.startswith(
                    (
                        ".",
                        "node_modules",
                        "venv",
                        ".venv",
                        "__pycache__",
                        "dist",
                        "build",
                    )
                )
                for part in path.parts
            ):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        match = pattern.search(line)
                        if match:
                            rel = path.relative_to(cwd)
                            todos.append(
                                f"- [{rel}:{i}] {match.group(1).upper()}: {match.group(2).strip()}"
                            )
                            if len(todos) >= limit:
                                return todos
            except Exception:
                continue
    return todos


def _find_files(cwd: Path, name: str) -> list[Path]:
    """Find a file in root and immediate subdirectories."""
    found = []
    root = cwd / name
    if root.exists():
        found.append(root)
    for subdir in cwd.iterdir():
        if subdir.is_dir() and not subdir.name.startswith("."):
            candidate = subdir / name
            if candidate.exists():
                found.append(candidate)
    return found


def _read_pyproject(cwd: Path) -> dict[str, Any]:
    for path in _find_files(cwd, "pyproject.toml"):
        try:
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            continue
    return {}


def _read_package_json(cwd: Path) -> dict[str, Any]:
    for path in _find_files(cwd, "package.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def _read_requirements(cwd: Path) -> list[str]:
    for path in _find_files(cwd, "requirements.txt"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]
        except Exception:
            continue
    return []


def _detect_stack(cwd: Path) -> list[str]:
    stack = []
    pyproject = _read_pyproject(cwd)
    package = _read_package_json(cwd)

    if pyproject:
        stack.append("Python")
        deps = pyproject.get("project", {}).get("dependencies", [])
        dep_names = [d.split()[0].split("=")[0].split("[")[0].lower() for d in deps]
        if any("fastapi" in d for d in dep_names):
            stack.append("FastAPI")
        if any("django" in d for d in dep_names):
            stack.append("Django")
        if any("flask" in d for d in dep_names):
            stack.append("Flask")
        if any("typer" in d for d in dep_names):
            stack.append("Typer")
        if any("uvicorn" in d for d in dep_names):
            stack.append("Uvicorn")
        if any("pytest" in d for d in dep_names):
            stack.append("pytest")

    if package:
        stack.append("Node.js")
        deps = list(package.get("dependencies", {}).keys())
        dev_deps = list(package.get("devDependencies", {}).keys())
        all_deps = deps + dev_deps
        if any("next" in d for d in all_deps):
            stack.append("Next.js")
        if any("react" in d for d in all_deps):
            stack.append("React")
        if any("vue" in d for d in all_deps):
            stack.append("Vue")
        if any("tailwind" in d for d in all_deps):
            stack.append("Tailwind CSS")
        if any("typescript" in d for d in all_deps):
            stack.append("TypeScript")

    if (cwd / "docker-compose.yml").exists() or (cwd / "Dockerfile").exists():
        stack.append("Docker")

    if (cwd / "kivy" / "buildozer.spec").exists() or (cwd / "buildozer.spec").exists():
        stack.append("Kivy / Buildozer")

    # Deduplicate preserving order
    seen = set()
    return [s for s in stack if not (s in seen or seen.add(s))]


def _list_top_level(cwd: Path) -> list[str]:
    items = []
    for path in sorted(cwd.iterdir()):
        if path.name.startswith(".") and path.name != ".github":
            continue
        if path.is_dir():
            items.append(f"{path.name}/")
        else:
            items.append(path.name)
    return items


def _read_readme(cwd: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        path = cwd / name
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                return "\n".join(lines[:MAX_README_LINES])
            except Exception:
                return ""
    return ""


def _count_lines(cwd: Path) -> dict[str, int]:
    """Rough line counts by language extension."""
    counts: Counter[str] = Counter()
    for path in cwd.rglob("*"):
        if path.is_dir():
            continue
        if any(
            part.startswith(
                (".", "node_modules", "venv", ".venv", "__pycache__", "dist", "build")
            )
            for part in path.parts
        ):
            continue
        ext = path.suffix.lower()
        if ext in (
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".go",
            ".rs",
            ".java",
            ".cpp",
            ".c",
            ".h",
            ".html",
            ".css",
            ".md",
        ):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    counts[ext] += sum(1 for _ in f)
            except Exception:
                pass
    return dict(counts)


def generate_context(project_name: str, cwd: Path) -> str:
    """Generate a CONTEXT.md string for the project."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stack = _detect_stack(cwd)
    remote = _git_remote(cwd)
    branch = _git_branch(cwd)
    commits = _git_recent_commits(cwd)
    todos = _find_todos(cwd)
    top_level = _list_top_level(cwd)
    readme = _read_readme(cwd)
    line_counts = _count_lines(cwd)
    pyproject = _read_pyproject(cwd)
    package = _read_package_json(cwd)
    requirements = _read_requirements(cwd)

    lines = [
        f"# {project_name} — Context",
        "",
        f"_Generated by context-keeper on {now}._",
        "",
        "## Overview",
        "",
    ]

    if readme:
        lines.append(readme)
        lines.append("")
    else:
        lines.append(f"Project directory: `{cwd}`")
        lines.append("")

    if stack:
        lines.extend(["## Tech Stack", ""])
        for s in stack:
            lines.append(f"- {s}")
        lines.append("")

    if pyproject or package or requirements:
        lines.extend(["## Dependencies", ""])
        if pyproject:
            deps = pyproject.get("project", {}).get("dependencies", [])
            if deps:
                lines.append("**pyproject.toml:**")
                for d in deps[:10]:
                    lines.append(f"- `{d}`")
                if len(deps) > 10:
                    lines.append(f"- _...and {len(deps) - 10} more_")
                lines.append("")
        if requirements:
            lines.append("**requirements.txt:**")
            for d in requirements[:10]:
                lines.append(f"- `{d}`")
            if len(requirements) > 10:
                lines.append(f"- _...and {len(requirements) - 10} more_")
            lines.append("")
        if package:
            deps = list(package.get("dependencies", {}).keys())
            if deps:
                lines.append("**package.json:**")
                for d in deps[:10]:
                    lines.append(f"- `{d}`")
                if len(deps) > 10:
                    lines.append(f"- _...and {len(deps) - 10} more_")
                lines.append("")

    lines.extend(["## Project Structure", ""])
    for item in top_level[:30]:
        lines.append(f"- `{item}`")
    if len(top_level) > 30:
        lines.append(f"- _...and {len(top_level) - 30} more items_")
    lines.append("")

    if line_counts:
        lines.extend(["## Code Stats", ""])
        for ext, count in sorted(line_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]:
            lines.append(f"- `{ext}`: {count} lines")
        lines.append("")

    if remote or branch:
        lines.extend(["## Repository", ""])
        if remote:
            lines.append(f"- Remote: `{remote}`")
        if branch:
            lines.append(f"- Branch: `{branch}`")
        lines.append("")

    if commits:
        lines.extend(["## Recent Commits", ""])
        for c in commits:
            lines.append(f"- {c}")
        lines.append("")

    if todos:
        lines.extend(["## Open Items", ""])
        for t in todos:
            lines.append(t)
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "_Add manual notes here. They will be preserved across syncs._",
            "",
        ]
    )

    return "\n".join(lines)
