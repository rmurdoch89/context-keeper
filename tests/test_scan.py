"""Tests for the filesystem scanner."""

from pathlib import Path

from context_keeper.scan import KNOWN_CONTEXT_FILES, scan_directory


class TestScanDirectory:
    def test_finds_known_context_files(self, tmp_path: Path):
        (tmp_path / "AGENTS.md").write_text("test")
        (tmp_path / "CLAUDE.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "AGENTS.md" in names
        assert "CLAUDE.md" in names

    def test_skips_unknown_files(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "README.md" not in names

    def test_finds_cursorrules(self, tmp_path: Path):
        """Regression: .cursorrules should be found (not ignored as dot-file)."""
        (tmp_path / ".cursorrules").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert ".cursorrules" in names

    def test_finds_copilot_instructions_in_github(self, tmp_path: Path):
        """Regression: .github/copilot-instructions.md should be found."""
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "copilot-instructions.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "copilot-instructions.md" in names

    def test_skips_git_dir(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "AGENTS.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "AGENTS.md" not in names

    def test_skips_venv_dir(self, tmp_path: Path):
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "AGENTS.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "AGENTS.md" not in names

    def test_skips_node_modules(self, tmp_path: Path):
        nm_dir = tmp_path / "node_modules"
        nm_dir.mkdir()
        (nm_dir / "AGENTS.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "AGENTS.md" not in names

    def test_skips_pytest_cache(self, tmp_path: Path):
        cache_dir = tmp_path / ".pytest_cache"
        cache_dir.mkdir()
        (cache_dir / "AGENTS.md").write_text("test")

        results = scan_directory(tmp_path)
        names = {r["name"] for r in results}
        assert "AGENTS.md" not in names

    def test_respects_max_depth(self, tmp_path: Path):
        sub = tmp_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        (sub / "AGENTS.md").write_text("test")

        results = scan_directory(tmp_path, max_depth=1)
        names = {r["name"] for r in results}
        assert "AGENTS.md" not in names

        results = scan_directory(tmp_path, max_depth=4)
        names = {r["name"] for r in results}
        assert "AGENTS.md" in names

    def test_marks_tracked_files(self, tmp_path: Path):
        from context_keeper.config import Config

        (tmp_path / "CLAUDE.md").write_text("test")
        config = Config(
            markless={"url": "", "username": "", "password": ""},
            projects={
                "demo": {
                    "local": str(tmp_path),
                    "remote": {"book": "B", "section": "S"},
                    "files": ["CLAUDE.md"],
                }
            },
        )

        results = scan_directory(tmp_path, config=config)
        claude_result = next(r for r in results if r["name"] == "CLAUDE.md")
        assert "tracked" in claude_result["status"]

    def test_dotfiles_in_known_context_files(self):
        assert ".cursorrules" in KNOWN_CONTEXT_FILES
        assert ".aider.conf.yml" in KNOWN_CONTEXT_FILES
