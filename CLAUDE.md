# CLAUDE.md — context-keeper

## Project overview

A small Python CLI that keeps AI coding context files in sync across machines.

- **Stack:** Python 3.12, Typer, Pydantic, httpx, PyYAML, Rich
- **Storage:** Markless (markdown library running on the Windows work PC)
- **Files managed:** `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`

## Architecture

```
src/context_keeper/
├── __init__.py      # version
├── cli.py           # Typer CLI commands
├── config.py        # YAML config loading (Pydantic)
├── markless.py      # HTTP client for Markless API
├── sync.py          # pull/push/sync + conflict detection + backups
└── generate.py      # repo metadata → CONTEXT.md generator
```

## Data flow

1. User edits `~/Projects/<project>/AGENTS.md` on Linux.
2. `ck push <project>` uploads it to `Context/<project>/AGENTS.md` in Markless.
3. On Windows, `ck pull <project>` downloads it to the configured `local` path — ideally the actual project root.
4. Both agents now read the same context.

The `files` list in config controls which files are synced. Add `.cursorrules`, `CONVENTIONS.md`, or any other agent context file as needed.

## Configuration

Config lives at `~/.config/context-keeper/config.yaml`:

```yaml
markless:
  url: https://markless.rumbo.dev
  username: rob
  password: "..."

projects:
  os-agent:
    local: ~/Projects/os-agent
    remote:
      book: Context
      section: os-agent
    files:
      - AGENTS.md
      - CLAUDE.md
```

## Important implementation notes

- `/api/library/export` does **not** create parent directories, so writes use `/api/library/sync`.
- After a successful push, local file mtime is touched to match remote mtime so status shows `synced`.
- Backups are stored in `~/.local/share/context-keeper/backups/`.
- `ck generate` creates a `CONTEXT.md` from repo metadata; it does not overwrite unless `--write` is passed.
- `ck tui` launches a Textual TUI for interactive sync.
- `ck scan` discovers context files on the local filesystem.
- `ck diff` shows unified diffs between local and remote files.