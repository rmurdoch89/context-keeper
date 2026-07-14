"""context-keeper CLI."""

from __future__ import annotations

from pathlib import Path
from typing import List

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import __version__
from .config import (
    Config,
    ensure_dirs,
    flatten_rel_path,
    get_project,
    list_projects,
    load_config,
    unflatten_name,
)
from .diff import diff_project
from .generate import generate_context
from .markless import MarklessClient
from .scan import scan_directory
from .sync import (
    delete_files,
    get_status,
    pull as pull_files,
    push as push_files,
    sync as sync_files,
)
from .tui import run_tui

app = typer.Typer(
    name="ck",
    help="Context Keeper — sync AI context files across devices via Markless.",
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def _default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_tui()


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


@app.command(name="list")
def list_projects_cmd(
    config_path: Path | None = typer.Option(
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
        if p.dir:
            files = f"[dim]auto ({len(p.resolve_files())} .md files)[/dim]"
        else:
            files = ", ".join(p.files)
        table.add_row(name, str(p.local), remote, files)
    console.print(table)


@app.command()
def status(
    project: str = typer.Argument(..., help="Project name"),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show sync status for a project."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    try:
        with _load_client(config) as client:
            statuses = get_status(client, project, project_cfg)
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

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
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Download context files from Markless to local project."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    try:
        with _load_client(config) as client:
            actions = pull_files(client, config, project, project_cfg, force=force)
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

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
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Upload local context files to Markless."""
    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    try:
        with _load_client(config) as client:
            actions = push_files(client, config, project, project_cfg, force=force)
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

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
    config_path: Path | None = typer.Option(
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

    try:
        with _load_client(config) as client:
            actions = sync_files(
                client, config, project, project_cfg, strategy=strategy
            )
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

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
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Read a remote context file from Markless."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    try:
        with _load_client(config) as client:
            content = client.read_file(
                project_cfg.remote.book,
                project_cfg.remote.section,
                file,
            )
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)
    console.print(Markdown(f"# {file}\n\n{content}"))


@app.command()
def generate(
    project: str = typer.Argument(..., help="Project name"),
    write: bool = typer.Option(False, "--write", "-w", help="Write CONTEXT.md locally"),
    push: bool = typer.Option(
        False, "--push", "-p", help="Push generated CONTEXT.md to Markless"
    ),
    config_path: Path | None = typer.Option(
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
        try:
            with _load_client(config) as client:
                client.write_file(
                    project_cfg.remote.book,
                    project_cfg.remote.section,
                    "CONTEXT.md",
                    content,
                )
        except httpx.HTTPError as e:
            console.print(f"[red]Network error: {e}[/red]")
            raise typer.Exit(1)
        console.print(
            f"[green]Pushed CONTEXT.md to {project_cfg.remote.book}/{project_cfg.remote.section}[/green]"
        )


@app.command()
def clone(
    project: str = typer.Argument(..., help="Project name"),
    source: str = typer.Argument(..., help="Source file to copy from, e.g. AGENTS.md"),
    targets: List[str] = typer.Argument(
        ..., help="Target file(s) to create, e.g. CLAUDE.md"
    ),
    push: bool = typer.Option(
        False, "--push", "-p", help="Push the new files to Markless"
    ),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Copy a context file to other filename(s)."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    src_path = project_cfg.local / source
    if not src_path.exists():
        console.print(f"[red]Source file not found: {src_path}[/red]")
        raise typer.Exit(1)

    content = src_path.read_text(encoding="utf-8")
    for target in targets:
        dest_path = project_cfg.local / target
        dest_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Created {dest_path}[/green]")

    if push:
        ensure_dirs(config)
        try:
            with _load_client(config) as client:
                for target in targets:
                    client.write_file(
                        project_cfg.remote.book,
                        project_cfg.remote.section,
                        target,
                        content,
                    )
        except httpx.HTTPError as e:
            console.print(f"[red]Network error: {e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]Pushed {len(targets)} file(s) to Markless[/green]")


@app.command()
def scan(
    path: Path | None = typer.Argument(
        None, help="Directory to scan (default: current directory)"
    ),
    depth: int = typer.Option(
        4, "--depth", "-d", help="Maximum directory depth to scan"
    ),
    config_path: Path | None = typer.Option(
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
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Show differences between local and remote context files."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    try:
        with _load_client(config) as client:
            results = diff_project(client, project, project_cfg)
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

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
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Launch the interactive TUI."""
    run_tui(config_path=config_path)


@app.command()
def version():
    """Show version."""
    console.print(f"context-keeper {__version__}")


@app.command()
def delete(
    project: str = typer.Argument(..., help="Project name"),
    files: list[str] = typer.Argument(
        None, help="File(s) to delete (omit to delete all)"
    ),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete files from Markless."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    if not force:
        target = ", ".join(files) if files else "ALL files"
        confirmed = typer.confirm(f"Delete {target} from {project} on Markless?")
        if not confirmed:
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    try:
        with _load_client(config) as client:
            actions = delete_files(client, config, project, project_cfg, files=files)
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)

    for a in actions:
        console.print(f"[red]{a['file']}: deleted[/red]")


@app.command()
def watch(
    project: str = typer.Argument(..., help="Project name"),
    interval: int = typer.Option(
        5, "--interval", "-i", help="Poll interval in seconds"
    ),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Watch a project and auto-push on local changes."""
    import time

    config = load_config(config_path)
    ensure_dirs(config)
    project_cfg = get_project(config, project)

    console.print(f"[bold]Watching {project} for changes (every {interval}s)...[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")

    try:
        while True:
            with _load_client(config) as client:
                statuses = get_status(client, project, project_cfg)
                local_newer = [s for s in statuses if s.local_newer or s.local_only]
                if local_newer:
                    names = [s.name for s in local_newer]
                    console.print(
                        f"[yellow]Changes detected: {', '.join(names)}[/yellow]"
                    )
                    push_files(client, config, project, project_cfg)
                    console.print("[green]Pushed[/green]")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching[/dim]")
    except httpx.HTTPError as e:
        console.print(f"[red]Network error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def history(
    project: str = typer.Argument(..., help="Project name"),
    file: str = typer.Argument(
        None, help="File to show history for (omit to list all)"
    ),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
    restore: str | None = typer.Option(
        None, "--restore", "-r", help="Restore a specific backup timestamp"
    ),
):
    """Browse and restore file backups."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)
    backup_root = config.backup_dir / project

    if not backup_root.exists():
        console.print("[yellow]No backups found[/yellow]")
        raise typer.Exit(0)

    if restore:
        parts = restore.split("/", 1)
        if len(parts) < 2:
            console.print("[red]Usage: --restore safe_name/timestamp[/red]")
            raise typer.Exit(1)
        safe_name, ts = parts[0], parts[1]
        backup_dir = backup_root / safe_name / ts
        backup_file = backup_dir / Path(file or "").name
        dest = project_cfg.file_path(safe_name if project_cfg.dir else (file or ""))
        if not backup_file.exists():
            console.print(f"[red]Backup not found: {backup_file}[/red]")
            raise typer.Exit(1)
        dest.write_text(backup_file.read_text(encoding="utf-8"))
        console.print(f"[green]Restored {dest} from {ts}[/green]")
        return

    if file:
        safe_name = flatten_rel_path(file) if project_cfg.dir else file
        backup_dirs = (
            sorted((backup_root / safe_name).iterdir(), reverse=True)
            if (backup_root / safe_name).exists()
            else []
        )
        table = Table("Timestamp", "Size")
        for d in backup_dirs[:20]:
            f = d / Path(file).name
            size = f.stat().st_size if f.exists() else 0
            table.add_row(d.name, f"{size} bytes")
        console.print(f"[bold]History for {file}[/bold]")
        console.print(table)
    else:
        table = Table("File", "Versions", "Latest")
        for safe_name in sorted(d.name for d in backup_root.iterdir() if d.is_dir()):
            versions = sorted((backup_root / safe_name).iterdir())
            if versions:
                latest = versions[-1].name
                table.add_row(safe_name, str(len(versions)), latest)
        console.print(table)


@app.command()
def hook(
    project: str = typer.Argument(..., help="Project name"),
    install: bool = typer.Option(
        False, "--install", "-i", help="Install post-commit hook"
    ),
    uninstall: bool = typer.Option(False, "--uninstall", "-u", help="Remove the hook"),
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """Install a git post-commit hook to auto-push context files."""
    config = load_config(config_path)
    project_cfg = get_project(config, project)

    git_dir = project_cfg.local / ".git"
    hook_path = git_dir / "hooks" / "post-commit"

    if uninstall:
        if hook_path.exists():
            hook_path.unlink()
            console.print(f"[green]Removed hook from {hook_path}[/green]")
        else:
            console.print("[yellow]No hook installed[/yellow]")
        return

    if not install:
        if hook_path.exists():
            console.print(f"[green]Hook installed at {hook_path}[/green]")
        else:
            console.print(
                "[yellow]No hook installed. Use --install to add one.[/yellow]"
            )
        return

    if not git_dir.exists():
        console.print(f"[red]Not a git repository: {project_cfg.local}[/red]")
        raise typer.Exit(1)

    hook_content = f'''#!/bin/sh
# context-keeper auto-push hook for {project}
ck push {project} --config "{config_path or "~/.config/context-keeper/config.yaml"}"
'''

    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)
    console.print(f"[green]Installed post-commit hook for {project}[/green]")


@app.command()
def skills(
    config_path: Path | None = typer.Option(
        None, "--config", "-c", help="Path to config file"
    ),
):
    """List all synced skills."""
    config = load_config(config_path)
    table = Table("Skill", "File", "Used by")

    for name in list_projects(config):
        project = config.projects[name]
        if not project.dir:
            continue
        for file_name in project.resolve_files():
            if not file_name.endswith("_SKILL.md") and not file_name.endswith(
                "_skill.md"
            ):
                continue
            rel_path = unflatten_name(file_name)
            skill_name = rel_path.removesuffix("/SKILL.md").removesuffix("/skill.md")
            table.add_row(skill_name, file_name, "OpenCode, Claude Code")
    console.print(table)


def entry() -> None:
    app()


if __name__ == "__main__":
    entry()
