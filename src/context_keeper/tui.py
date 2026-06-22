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

from .config import Config, ProjectConfig, ensure_dirs, list_projects, load_config
from .generate import generate_context
from .markless import MarklessClient
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

    def watch_project_name(self, name: str | None) -> None:
        title = self.query_one("#detail-title", Static)
        if name:
            title.update(f"# {name}")
        else:
            title.update("Select a project")

    def watch_project_state(self, state: list[dict[str, Any]]) -> None:
        md = self.query_one("#detail-content", Markdown)
        if not state:
            md.update("No project selected.")
            return

        lines = ["## File Status", ""]
        for s in state:
            file = s["name"]
            status = s["status"]
            local = s.get("local", "missing")
            remote = s.get("remote", "missing")
            lines.append(f"**{file}** — {status}")
            lines.append(f"- Local:  `{local}`")
            lines.append(f"- Remote: `{remote}`")
            lines.append("")
        md.update("\n".join(lines))


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
        list_view = self.query_one("#project-list", ListView)
        list_view.clear()
        self.project_states.clear()

        if not self.client or not self.config:
            return

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
            self.project_states[name] = state
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
            return "synced"
        if any("newer" in s for s in statuses):
            return "conflict"
        if any(s == "local only" for s in statuses):
            return "local only"
        if any(s == "remote only" for s in statuses):
            return "remote only"
        return "mixed"

    @on(ListView.Selected)
    @on(ListView.Highlighted)
    def _show_detail(self) -> None:
        list_view = self.query_one("#project-list", ListView)
        item = list_view.highlighted_child
        detail = self.query_one(ProjectDetail)
        if item is None:
            detail.project_name = None
            detail.project_state = []
            return
        name = item.project_name
        detail.project_name = name
        detail.project_state = self.project_states.get(name, [])

    def _selected_project(self) -> tuple[str, ProjectConfig] | None:
        list_view = self.query_one("#project-list", ListView)
        item = list_view.highlighted_child
        if item is None:
            return None
        name = item.project_name
        return name, self.projects[name]

    def _notify(self, message: str) -> None:
        self.notify(message, title="context-keeper", timeout=3)

    def action_refresh(self) -> None:
        self.refresh_projects()
        self._notify("Refreshed")

    def action_pull(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        pull_files(self.client, self.config, name, project)
        self.refresh_projects()
        self._notify(f"Pulled {name}")

    def action_push(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        push_files(self.client, self.config, name, project)
        self.refresh_projects()
        self._notify(f"Pushed {name}")

    def action_sync(self) -> None:
        selected = self._selected_project()
        if not selected or not self.client or not self.config:
            return
        name, project = selected
        sync_files(self.client, self.config, name, project, strategy="newest")
        self.refresh_projects()
        self._notify(f"Synced {name}")

    def action_generate(self) -> None:
        selected = self._selected_project()
        if not selected:
            return
        name, project = selected
        content = generate_context(name, project.local)
        ctx_path = project.local / "CONTEXT.md"
        ctx_path.write_text(content, encoding="utf-8")
        if self.client and self.config:
            ensure_dirs(self.config)
            push_files(self.client, self.config, name, project)
        self.refresh_projects()
        self._notify(f"Generated CONTEXT.md for {name}")

    def on_unmount(self) -> None:
        if self.client:
            self.client.close()


def run_tui(config_path: Path | None = None) -> None:
    app = ContextKeeperApp(config_path=config_path)
    app.run()
