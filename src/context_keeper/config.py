"""Configuration loading and validation."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "context-keeper" / "config.yaml"
DEFAULT_BACKUP_DIR = Path.home() / ".local" / "share" / "context-keeper" / "backups"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "context-keeper" / "state"


class MarklessConfig(BaseModel):
    url: str = ""
    username: str = ""
    password: str = ""


class RemotePath(BaseModel):
    book: str
    section: str


class ProjectConfig(BaseModel):
    local: Path
    remote: RemotePath
    files: list[str] = Field(default_factory=list)
    dir: str | None = None
    mirror: Path | None = None

    @field_validator("local", "mirror", mode="before")
    @classmethod
    def expand_path(cls, value: Any) -> Any:
        if value is None:
            return None
        return Path(os.path.expandvars(os.path.expanduser(str(value))))

    def resolve_files(self) -> list[str]:
        """Return the effective file list, expanding dir if set.

        For dir-based projects, returns flat names using _ instead of /
        since Markless does not support / in filenames.
        """
        if self.dir:
            scan_root = self.local
            scan_dir = scan_root / self.dir
            if not scan_dir.exists():
                return []
            md_files = []
            for p in sorted(scan_dir.rglob("*.md")):
                parts = p.relative_to(scan_dir).parts
                if any(part.startswith(".") for part in parts):
                    continue
                rel = str(p.relative_to(scan_root).as_posix())
                md_files.append(rel.replace("/", "_"))
            return md_files
        return list(self.files)

    def file_path(self, name: str) -> Path:
        """Resolve a file name to its local path."""
        if self.dir is not None:
            return self.local / name.replace("_", "/")
        return self.local / name


class Config(BaseModel):
    markless: MarklessConfig = Field(default_factory=MarklessConfig)
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    backup_dir: Path = DEFAULT_BACKUP_DIR
    state_dir: Path = DEFAULT_STATE_DIR

    @field_validator("backup_dir", "state_dir", mode="before")
    @classmethod
    def expand_path(cls, value: Any) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(str(value))))


def _prompt_for_credentials(config: Config) -> None:
    """Prompt interactively for missing Markless credentials."""
    if config.markless.username and config.markless.password:
        return

    if not sys.stdin.isatty():
        raise RuntimeError(
            "Markless credentials are missing and stdin is not a TTY. "
            "Set them in the config file or via the MARKLESS_PASSWORD environment variable."
        )

    if not config.markless.username:
        config.markless.username = input("Markless username: ").strip()
        if not config.markless.username:
            raise ValueError("Username is required")

    if not config.markless.password:
        config.markless.password = getpass.getpass("Markless password: ").strip()
        if not config.markless.password:
            raise ValueError("Password is required")


def load_config(path: Path | None = None, prompt: bool = True) -> Config:
    """Load config from YAML file.

    If prompt is True (the default), missing credentials are requested
    interactively via the terminal. Set prompt to False when the caller
    will collect credentials itself (e.g. the TUI).
    """
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Create one with: cp config.example.yaml {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = Config.model_validate(raw)

    env_password = os.environ.get("MARKLESS_PASSWORD")
    if env_password:
        config.markless.password = env_password

    if prompt:
        _prompt_for_credentials(config)

    return config


def ensure_dirs(config: Config) -> None:
    """Create backup and state directories if needed."""
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    config.state_dir.mkdir(parents=True, exist_ok=True)


def list_projects(config: Config) -> list[str]:
    """Return sorted list of configured project names."""
    return sorted(config.projects.keys())


def get_project(config: Config, name: str) -> ProjectConfig:
    """Get project config by name."""
    if name not in config.projects:
        raise KeyError(
            f"Unknown project: {name}. Configured: {', '.join(list_projects(config))}"
        )
    return config.projects[name]
