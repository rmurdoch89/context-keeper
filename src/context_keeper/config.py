"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "context-keeper" / "config.yaml"
DEFAULT_BACKUP_DIR = Path.home() / ".local" / "share" / "context-keeper" / "backups"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "context-keeper" / "state"


class MarklessConfig(BaseModel):
    url: str = "https://markless.rumbo.dev"
    username: str = "rob"
    password: str = ""


class RemotePath(BaseModel):
    book: str
    section: str


class ProjectConfig(BaseModel):
    local: Path
    remote: RemotePath
    files: list[str] = Field(
        default_factory=lambda: ["AGENTS.md", "CLAUDE.md", "CONTEXT.md"]
    )
    generate: bool = True

    @field_validator("local", mode="before")
    @classmethod
    def expand_local_path(cls, value: Any) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(str(value))))


class Config(BaseModel):
    markless: MarklessConfig = Field(default_factory=MarklessConfig)
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    backup_dir: Path = DEFAULT_BACKUP_DIR
    state_dir: Path = DEFAULT_STATE_DIR

    @field_validator("backup_dir", "state_dir", mode="before")
    @classmethod
    def expand_path(cls, value: Any) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(str(value))))


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file."""
    config_path = path or DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found: {config_path}\n"
            f"Create one with: cp config.example.yaml {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return Config.model_validate(raw)


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
