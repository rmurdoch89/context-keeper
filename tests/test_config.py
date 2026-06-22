"""Tests for context-keeper config loading."""

from pathlib import Path

import yaml

from context_keeper.config import Config, load_config


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
