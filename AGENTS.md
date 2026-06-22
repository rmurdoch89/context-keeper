# Agent Guidance for context-keeper

## Project purpose

context-keeper is a Python CLI that syncs AI context files (`AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`) across devices using Markless as the canonical store.

## Conventions

- Use `uv` for dependency management.
- Target Python 3.12+.
- Follow the existing code style; run `uv run ruff check src/` and `uv run ruff format src/` before committing.
- Keep the Markless client thin and deterministic.
- Backup files before overwriting them.
- Treat Markless as the source of truth for conflicts.

## Common commands

```bash
# Run CLI in dev
uv run ck list
uv run ck status <project>
uv run ck pull <project>
uv run ck push <project>
uv run ck sync <project>
uv run ck generate <project> --write --push

# Lint/format
uv run ruff check src/
uv run ruff format src/
```

## Markless API endpoints used

- `GET /api/library/tree`
- `GET /api/library/file?book=&section=&file=`
- `POST /api/library/sync` (used for writes because `/export` does not create parent dirs)

Auth is HTTP Basic Auth via the config file.
