# context-keeper

Sync AI context files across devices via [Markless](https://markless.rumbo.dev).

## Which files?

context-keeper syncs whatever markdown files your AI agents read. Common ones:

| File | Used by |
|------|---------|
| `AGENTS.md` | Kimi Code, OpenCode |
| `CLAUDE.md` | Claude Code |
| `.cursorrules` | Cursor |
| `CONVENTIONS.md` | Aider, generic |
| `CONTEXT.md` | Your own project brief |

You list the files per project in `~/.config/context-keeper/config.yaml`. Add or remove files any time.

## How it works

- **Markless is the source of truth.** Context files live under `Context/<project>/` in Markless.
- **Each device has its own local paths.** On Linux `local` might be `~/Projects/barnos`; on Windows it might be `C:\Users\Rob\barnos`.
- **`ck push`** uploads local files to Markless.
- **`ck pull`** downloads them to the local project directory.
- **`ck sync`** picks the newest version and backs up whatever gets overwritten.

## Install

```bash
cd ~/Projects/context-keeper
uv sync
```

## Configure

```bash
mkdir -p ~/.config/context-keeper
cp config.example.yaml ~/.config/context-keeper/config.yaml
# edit with your projects and file lists
```

## Usage

```bash
# List projects
ck list

# Check sync status
ck status barnos

# Pull remote context to local project
ck pull barnos

# Push local context to remote
ck push barnos

# Bidirectional sync (newest wins)
ck sync barnos

# Force overwrite
ck pull barnos --force
ck push barnos --force

# Read remote file without syncing
ck read barnos CLAUDE.md

# Generate CONTEXT.md from repo metadata
ck generate barnos --write --push

# Launch interactive TUI
ck tui

# Scan for context files on this machine
ck scan ~/Projects

# Show local vs remote diff
ck diff barnos

# Clone a context file to other filenames
ck clone barnos AGENTS.md CLAUDE.md CONVENTIONS.md --push
```

## Cross-device workflow

1. On Linux: edit `~/Projects/barnos/AGENTS.md`, run `ck push barnos`
2. On Windows: open a new PowerShell window in the project folder, run `ck pull barnos`
3. Claude Code now sees the updated `CLAUDE.md` in the project root.

The key is that `local` in the config should point to the **actual project root** on each device. If a project only exists on one machine, point it to a reference folder like `C:\Users\Rob\Context\<project>` on Windows.

## Windows work PC setup

context-keeper runs inside WSL Ubuntu-24.04. A PowerShell profile function lets you run `ck` from any PowerShell window.

Pulled files are written to the path in your Windows config. If that path is the actual project root, Claude Code finds them automatically.

If `ck` is not recognized, reload the profile:

```powershell
. $PROFILE
```

Or run directly via WSL:

```bash
wsl -d Ubuntu-24.04 -u rob /home/rob/.local/bin/ck version
```

## Interactive TUI

Run `ck tui` for a terminal UI that shows all projects, their sync status, and lets you pull/push/sync/generate with keys:

- `p` — pull selected project
- `P` — push selected project
- `s` — sync selected project
- `g` — generate CONTEXT.md
- `c` — clone an existing file to fill in missing ones
- `r` — refresh status
- `q` — quit

## Scanning for context files

Find all AI context files on the current machine and see which ones are tracked:

```bash
ck scan ~/Projects
ck scan ~/Projects --depth 3
ck scan "C:\Users\Rob" --depth 2    # Windows paths auto-convert in WSL
```

This finds `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `.cursorrules`, `CONVENTIONS.md`, etc.

## Diff local vs remote

Before syncing, see what changed:

```bash
ck diff barnos
```

## Adding a new AI agent

If you start using an agent that needs a different file — say `.cursorrules` — just add it to the `files` list in `config.yaml` and run `ck sync`.
