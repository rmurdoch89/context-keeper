"""context-keeper CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import __version__
from .config import Config, ensure_dirs, get_project, list_projects, load_config
from .diff import diff_project
from .generate import generate_context
from .markless import MarklessClient
from .scan import scan_directory
from .sync import get_status, pull as pull_files, push as push_files, sync as sync_files
from .tui import run_tui

app = typer.Typer(
    name="ck",
    help="Context Keeper — sync AI context files across devices via Markless.",
    no_args_is_help=True,
)
console = Console()


def _load_client(config: Config) -> MarklessClient:
    return MarklessClient(
        url=config.markless.url,
        username=config.markless.username,
        password=config.markless.password,
    )


def _normalize_path(path: Path) -> Path:
    """Convert Windows paths to WSL paths when running under WSL."""
    s = str(path).replace("\\\\", "\\")
    if len(s) >= 2 and s[1] == ":":
        # C:\foo -> /mnt/c/foo
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/")
        return Path(f"/mnt/{drive}{rest}")
    return path


@app.command()
def list(
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """List configured projects."""
    config = load_config(config_path)
    projects = list_projects(config)
    if not projects:
        console.print("[yellow]No projects configured.[/yellow]")
        raise typer.Exit(0)

    table = Table("Project", "Local Path", "Remote Book/Section", "Files")
    for name in projects:
        p = config.projects[name]
        remote = f"{p.remote.book}/{p.remote.section}"
        files = ", ".join(p.files)
        table.add_row(name, str(p.local), remote, files)
    console.print(table)


@app.command()
def status(
    project: str = typer.Argument(..., help="Project name"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show sync status for a project."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        statuses = get_status(client, project, project_cfg)

    table = Table("File", "Local", "Remote", "State")
    for s in statuses:
        local_str = "missing"
        remote_str = "missing"
        if s.local_exists and s.local_mtime:
            local_str = s.local_mtime.strftime("%Y-%m-%d %H:%M:%S UTC")
        if s.remote_exists and s.remote_mtime:
            remote_str = s.remote_mtime.strftime("%Y-%m-%d %H:%M:%S UTC")

        if not s.local_exists and not s.remote_exists:
            state = "[dim]missing both[/dim]"
        elif s.synced:
            state = "[green]synced[/green]"
        elif s.local_only:
            state = "[cyan]local only[/cyan]"
        elif s.remote_only:
            state = "[magenta]remote only[/magenta]"
        elif s.local_newer:
            state = "[yellow]local newer[/yellow]"
        elif s.remote_newer:
            state = "[yellow]remote newer[/yellow]"
        else:
            state = "[dim]unknown[/dim]"

        table.add_row(s.name, local_str, remote_str, state)

    console.print(table)


@app.command()
def pull(
    project: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite local even if newer"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Download context files from Markless to local project."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        actions = pull_files(client, config, project, project_cfg, force=force)

    for a in actions:
        if a["action"] == "skipped":
            console.print(f"[dim]{a['file']}: skipped ({a.get('reason', '')})[/dim]")
        else:
            console.print(f"[green]{a['file']}: {a['action']}[/green]")


@app.command()
def push(
    project: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite remote even if newer"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Upload local context files to Markless."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        actions = push_files(client, config, project, project_cfg, force=force)

    for a in actions:
        if a["action"] == "skipped":
            console.print(f"[dim]{a['file']}: skipped ({a.get('reason', '')})[/dim]")
        else:
            console.print(f"[green]{a['file']}: {a['action']}[/green]")


@app.command("sync")
def sync_cmd(
    project: str = typer.Argument(..., help="Project name"),
    strategy: str = typer.Option(
        "newest", "--strategy", "-s", help="Conflict strategy: newest, local, remote"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Bidirectional sync using the chosen conflict strategy."""
    if strategy not in ("newest", "local", "remote"):
        console.print("[red]Strategy must be one of: newest, local, remote[/red]")
        raise typer.Exit(1)

    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        actions = sync_files(client, config, project, project_cfg, strategy=strategy)

    for a in actions:
        if a["action"] == "skipped":
            console.print(f"[dim]{a['file']}: skipped ({a.get('reason', '')})[/dim]")
        elif a["action"] == "unchanged":
            console.print(f"[dim]{a['file']}: unchanged[/dim]")
        else:
            console.print(f"[green]{a['file']}: {a['action']}[/green]")


@app.command()
def read(
    project: str = typer.Argument(..., help="Project name"),
    file: str = typer.Argument(..., help="Context file name, e.g. AGENTS.md"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Read a remote context file from Markless."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        content = client.read_file(
            project_cfg.remote.book,
            project_cfg.remote.section,
            file,
        )
    console.print(Markdown(f"# {file}\n\n{content}"))


@app.command()
def generate(
    project: str = typer.Argument(..., help="Project name"),
    write: bool = typer.Option(False, "--write", "-w", help="Write CONTEXT.md locally"),
    push: bool = typer.Option(
        False, "--push", "-p", help="Push generated CONTEXT.md to Markless"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Generate a CONTEXT.md from repository metadata."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    content = generate_context(project, project_cfg.local)

    if not write and not push:
        console.print(Markdown(content))
        console.print("\n[dim]Use --write to save locally or --push to upload.[/dim]")
        return

    if write or push:
        ctx_path = project_cfg.local / "CONTEXT.md"
        ctx_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote {ctx_path}[/green]")

    if push:
        ensure_dirs(config)
        with _load_client(config) as client:
            client.write_file(
                project_cfg.remote.book,
                project_cfg.remote.section,
                "CONTEXT.md",
                content,
            )
        console.print(
            f"[green]Pushed CONTEXT.md to {project_cfg.remote.book}/{project_cfg.remote.section}[/green]"
        )


@app.command()
def scan(
    path: Optional[Path] = typer.Argument(
        None, help="Directory to scan (default: current directory)"
    ),
    depth: int = typer.Option(
        4, "--depth", "-d", help="Maximum directory depth to scan"
    ),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Scan for AI context files on this machine."""
    target = _normalize_path(path or Path.cwd())
    if not target.exists():
        console.print(f"[red]Path not found: {target}[/red]")
        raise typer.Exit(1)

    config = None
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        pass

    results = scan_directory(target, config=config, max_depth=depth)
    if not results:
        console.print(f"[yellow]No context files found under {target}[/yellow]")
        raise typer.Exit(0)

    table = Table("File", "Path", "Status")
    for r in results:
        table.add_row(r["name"], str(r["path"]), r["status"])
    console.print(table)
    console.print(f"[dim]{len(results)} context file(s) found[/dim]")


@app.command()
def diff(
    project: str = typer.Argument(..., help="Project name"),
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show differences between local and remote context files."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    with _load_client(config) as client:
        results = diff_project(client, project, project_cfg)

    for r in results:
        console.print(f"[bold]{r['file']}[/bold]")
        if not r["local_exists"]:
            console.print("  [magenta]missing locally[/magenta]")
        elif not r["remote_exists"]:
            console.print("  [cyan]missing remotely[/cyan]")
        elif r["diff"]:
            console.print(Markdown(f"```diff\n{r['diff']}\n```"))
        else:
            console.print("  [green]no differences[/green]")
        console.print()


@app.command()
def tui(
    config_path: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Launch the interactive TUI."""
    run_tui(config_path=config_path)


@app.command()
def version():
    """Show version."""
    console.print(f"context-keeper {__version__}")


def entry() -> None:
    app()


if __name__ == "__main__":
    entry()
