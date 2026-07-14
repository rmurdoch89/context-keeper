"""Tests for context-keeper config loading."""

from pathlib import Path

import pytest
import yaml

from context_keeper.config import (
    Config,
    ProjectConfig,
    flatten_rel_path,
    load_config,
    unflatten_name,
)


def test_load_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    data = {
        "markless": {
            "url": "https://example.com",
            "username": "user",
            "password": "pass",
        },
        "projects": {
            "demo": {
                "local": "~/Projects/demo",
                "remote": {"book": "Context", "section": "demo"},
                "files": ["AGENTS.md"],
            }
        },
    }
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    cfg = load_config(config_path)
    assert isinstance(cfg, Config)
    assert cfg.markless.url == "https://example.com"
    assert "demo" in cfg.projects
    assert cfg.projects["demo"].local.name == "demo"
    assert cfg.projects["demo"].remote.book == "Context"


@pytest.mark.parametrize(
    "rel_path",
    [
        "AGENTS.md",
        "skills/foo.md",
        "reflex-docs/SKILL.md",
        "my_docs/setup_notes.md",
        "a/b/c_d/e_f.md",
        "weird___name.md",
    ],
)
def test_flatten_unflatten_round_trip(rel_path: str) -> None:
    flat = flatten_rel_path(rel_path)
    assert unflatten_name(flat) == rel_path


def test_flatten_preserves_existing_no_underscore_names() -> None:
    # Files with no literal underscores must flatten to the same name as
    # before, so already-synced remote files keep matching.
    assert flatten_rel_path("skills/foo.md") == "skills_foo.md"


def test_file_path_dir_mode_resolves_underscore_filename(tmp_path: Path) -> None:
    project = ProjectConfig(
        local=tmp_path,
        remote={"book": "Context", "section": "demo"},
        dir="skills",
    )
    assert project.file_path("my__docs_setup__notes.md") == (
        tmp_path / "my_docs" / "setup_notes.md"
    )
