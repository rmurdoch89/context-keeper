"""Textual TUI for context-keeper."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)
from textual import work

from .config import Config, ProjectConfig, ensure_dirs, list_projects, load_config
from .generate import generate_context
from .markless import MarklessClient
from .scan import tool_for
from .sync import get_status, pull as pull_files, push as push_files, sync as sync_files


class ProjectListItem(ListItem):
    """List item showing project name and sync state."""

    def __init__(self, name: str, state: str) -> None:
        super().__init__(Label(f"{name:20} {state}"))
        self.project_name = name


class ProjectDetail(Vertical):
    """Detail view for the selected project."""

    project_name: reactive[str | None] = reactive(None)
    project_state: reactive[list[dict[str, Any]]] = reactive([])

    def compose(self) -> ComposeResult:
        yield Static("Select a project", id="detail-title")
        yield Markdown("", id="detail-content")
        yield Markdown("", id="detail-guidance")

    def watch_project_name(self, name: str | None) -> None:
        title = self.query_one("#detail-title", Static)
        if name:
            title.update(f"# {name}")
        else:
            title.update("Select a project")

    def watch_project_state(self, state: list[dict[str, Any]]) -> None:
        md = self.query_one("#detail-content", Markdown)
        guide = self.query_one("#detail-guidance", Markdown)
        if not state:
            md.update("No project selected.")
            guide.update("")
            return

        lines = ["## File Status", ""]
        for s in state:
            file = s["name"]
            status = s["status"]
            local = s.get("local", "missing")
            remote = s.get("remote", "missing")
            icon = {
                "synced": "✓",
                "local only": "+",
                "remote only": "↓",
                "local newer": "↑",
                "remote newer": "↓",
                "missing both": "✗",
            }.get(status, "?")
            tool = tool_for(file)
            tool_str = f" ({tool})" if tool else ""
            lines.append(f"{icon} **{file}** — {status}{tool_str}")
            lines.append(f"  Local:  `{local}`")
            lines.append(f"  Remote: `{remote}`")
            lines.append("")
        md.update("\n".join(lines))

        guide.update(self._guidance(state))

    @staticmethod
    def _guidance(state: list[dict[str, Any]]) -> str:
        statuses = [s["status"] for s in state]
        synced = sum(1 for s in statuses if s == "synced")
        total = len(statuses)
        missing_both = sum(1 for s in statuses if s == "missing both")
        local_newer = sum(1 for s in statuses if s in ("local newer", "local only"))
        remote_newer = sum(1 for s in statuses if s in ("remote newer", "remote only"))

        lines = ["---", "## What to do", ""]

        if synced == total:
            lines.append("All files synced. Nothing to do.")
            return "\n".join(lines)

        if missing_both == total:
            lines.append("No files exist yet. Create them locally, then `push`.")
            return "\n".join(lines)

        if missing_both > 0:
            missing = [s["name"] for s in state if s["status"] == "missing both"]
            lines.append(f"Files missing on both sides: **{', '.join(missing)}**")
            lines.append("Create them locally first, then `push`.")
            lines.append("")

        if local_newer > 0:
            lines.append("You have local changes not yet on Markless.")
            lines.append("Run **push** (`P`) to upload them.")
            lines.append("")

        if remote_newer > 0:
            lines.append("Markless has changes not yet on this device.")
            lines.append("Run **pull** (`p`) to download them.")
            lines.append("")

        return "\n".join(lines)


class ContextKeeperApp(App[None]):
    """Main TUI application."""

    CSS = """
    Screen { align: center middle; }
    #main { width: 100%; height: 100%; }
    #sidebar { width: 35%; height: 100%; border: solid $primary; }
    #detail { width: 65%; height: 100%; border: solid $primary; padding: 1 2; }
    #detail-title { text-style: bold; margin-bottom: 1; }
    ListView { height: 100%; }
    ListView > ListItem {
        color: $text;
        height: auto;
        padding: 0 1;
    }
    ListView > ListItem.--highlight { background: $primary 30%; }
    """

    BINDINGS = [
        ("p", "pull", "Pull"),
        ("P", "push", "Push"),
        ("s", "sync", "Sync"),
        ("g", "generate", "Generate"),
        ("c", "clone", "Clone"),
        ("r", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.config_path = config_path
        self.config: Config | None = None
        self.client: MarklessClient | None = None
        self.projects: dict[str, ProjectConfig] = {}
        self.project_states: dict[str, list[dict[str, Any]]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield ListView(id="project-list")
            with Vertical(id="detail"):
                yield ProjectDetail()
        yield Footer()

    def on_mount(self) -> None:
        self.config = load_config(self.config_path)
        ensure_dirs(self.config)
        self.client = MarklessClient(
            url=self.config.markless.url,
            username=self.config.markless.username,
            password=self.config.markless.password,
        )
        self.projects = self.config.projects
        self.refresh_projects()

    def refresh_projects(self) -> None:
        """Schedule a background refresh of all project states."""
        list_view = self.query_one("#project-list", ListView)
        list_view.clear()
        list_view.append(ListItem(Label("[dim]Loading...[/dim]")))
        self._load_projects()

    @work(thread=True, exclusive=True)
    def _load_projects(self) -> None:
        """Fetch project states from Markless (runs in thread pool)."""
        if not self.client or not self.config:
            return
        try:
            project_states: dict[str, list[dict[str, Any]]] = {}
            for name in list_projects(self.config):
                project = self.projects[name]
                statuses = get_status(self.client, name, project)
                state = []
                for s in statuses:
                    state.append(
                        {
                            "name": s.name,
                            "status": self._status_label(s),
                            "local": s.local_mtime.strftime("%Y-%m-%d %H:%M UTC")
                            if s.local_mtime
                            else "missing",
                            "remote": s.remote_mtime.strftime("%Y-%m-%d %H:%M UTC")
                            if s.remote_mtime
                            else "missing",
                        }
                    )
                project_states[name] = state
            self.call_from_thread(self._apply_project_states, project_states)
        except Exception as e:
            self.call_from_thread(self._apply_project_states, {})
            self.call_from_thread(self._notify_error, f"Failed to load projects: {e}")

    def _apply_project_states(
        self, project_states: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Update list view with fetched states (runs on main thread)."""
        self.project_states = project_states
        list_view = self.query_one("#project-list", ListView)
        list_view.clear()
        for name, state in project_states.items():
            overall = self._overall_state(state)
            list_view.append(ProjectListItem(name, overall))
        if list_view.children:
            list_view.index = 0
            self._show_detail()

    def _status_label(self, s: Any) -> str:
        if not s.local_exists and not s.remote_exists:
            return "missing both"
        if s.synced:
            return "synced"
        if s.local_only:
            return "local only"
        if s.remote_only:
            return "remote only"
        if s.local_newer:
            return "local newer"
        if s.remote_newer:
            return "remote newer"
        return "unknown"

    def _overall_state(self, state: list[dict[str, Any]]) -> str:
        statuses = [s["status"] for s in state]
        if all(s == "synced" for s in statuses):
            return "[green]OK[/green]"
        if all(s == "missing both" for s in statuses):
            return "[dim]empty[/dim]"
        missing = sum(1 for s in statuses if s == "missing both")
        synced_count = sum(1 for s in statuses if s == "synced")
        if missing > 0 and missing + synced_count == len(statuses):
            return "[yellow]incomplete[/yellow]"
        if any("newer" in s or "only" in s for s in statuses):
            return "[red]out of sync[/red]"
        return "[yellow]mixed[/yellow]"

    @on(ListView.Highlighted)
    def _show_detail(self) -> None:
        list_view = self.query_one("#project-list", ListView)
        item = list_view.highlighted_child
        detail = self.query_one(ProjectDetail)
        if item is None or not isinstance(item, ProjectListItem):
            detail.project_name = None
            detail.project_state = []
            return
        name = item.project_name
        detail.project_name = name
        detail.project_state = self.project_states.get(name, [])

    def _selected_project(self) -> tuple[str, ProjectConfig] | None:
        list_view = self.query_one("#project-list", ListView)
        item = list_view.highlighted_child
        if item is None or not isinstance(item, ProjectListItem):
            return None
        name = item.project_name
        return name, self.projects[name]

    def _notify(self, message: str) -> None:
        self.notify(message, title="context-keeper", timeout=3)

    def _notify_error(self, message: str) -> None:
        self.notify(message, title="Error", severity="error", timeout=6)

    def action_refresh(self) -> None:
        self.refresh_projects()
        self._notify("Refreshing...")

    def action_pull(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        self._do_pull(name, project)

    @work(thread=True)
    def _do_pull(self, name: str, project: ProjectConfig) -> None:
        try:
            pull_files(self.client, self.config, name, project)
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify, f"Pulled {name}")
        except Exception as e:
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify_error, f"Pull failed: {e}")

    def action_push(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        self._do_push(name, project)

    @work(thread=True)
    def _do_push(self, name: str, project: ProjectConfig) -> None:
        try:
            push_files(self.client, self.config, name, project)
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify, f"Pushed {name}")
        except Exception as e:
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify_error, f"Push failed: {e}")

    def action_sync(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        self._do_sync(name, project)

    @work(thread=True)
    def _do_sync(self, name: str, project: ProjectConfig) -> None:
        try:
            sync_files(self.client, self.config, name, project, strategy="newest")
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify, f"Synced {name}")
        except Exception as e:
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify_error, f"Sync failed: {e}")

    def action_generate(self) -> None:
        selected = self._selected_project()
        if not selected:
            return
        name, project = selected
        self._do_generate(name, project)

    @work(thread=True)
    def _do_generate(self, name: str, project: ProjectConfig) -> None:
        try:
            content = generate_context(name, project.local)
            ctx_path = project.local / "CONTEXT.md"
            ctx_path.write_text(content, encoding="utf-8")
            if self.client and self.config:
                ensure_dirs(self.config)
                self.client.write_file(
                    project.remote.book,
                    project.remote.section,
                    "CONTEXT.md",
                    content,
                )
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify, f"Generated CONTEXT.md for {name}")
        except Exception as e:
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify_error, f"Generate failed: {e}")

    def action_clone(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected

        state = self.project_states.get(name, [])
        missing = [s["name"] for s in state if s["status"] == "missing both"]
        existing = [s["name"] for s in state if s["status"] != "missing both"]

        if not missing:
            self._notify(f"{name}: no missing files to create")
            return
        if not existing:
            self._notify(f"{name}: no existing file to clone from — create one first")
            return

        source = existing[0]
        src_path = project.local / source
        if not src_path.exists():
            self._notify(f"Source {source} not found on disk")
            return

        self._do_clone(name, project, source, src_path, missing)

    @work(thread=True)
    def _do_clone(
        self,
        name: str,
        project: ProjectConfig,
        source: str,
        src_path: Path,
        missing: list[str],
    ) -> None:
        try:
            content = src_path.read_text(encoding="utf-8")
            ensure_dirs(self.config)
            for target in missing:
                dest = project.local / target
                dest.write_text(content, encoding="utf-8")
                self.client.write_file(
                    project.remote.book, project.remote.section, target, content
                )
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify, f"Cloned {source} → {', '.join(missing)}")
        except Exception as e:
            self.call_from_thread(self.refresh_projects)
            self.call_from_thread(self._notify_error, f"Clone failed: {e}")

    def on_unmount(self) -> None:
        if self.client:
            self.client.close()


def run_tui(config_path: Path | None = None) -> None:
    app = ContextKeeperApp(config_path=config_path)
    app.run()
