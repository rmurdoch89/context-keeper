# context-keeper

Sync AI context files (`AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`) across devices via [Markless](https://markless.rumbo.dev).

## Why

You probably have:
- Kimi Code reading `AGENTS.md` on your Linux machine
- Claude Code reading `CLAUDE.md` on your Windows work PC
- Notes and voice memos in Mentic mentioning the project

`context-keeper` keeps those context files in one canonical place (Markless) and syncs them to each machine.

## Install

```bash
cd ~/Projects/context-keeper
uv sync
```

## Configure

```bash
mkdir -p ~/.config/context-keeper
cp config.example.yaml ~/.config/context-keeper/config.yaml
# edit with your projects
```

## Usage

```bash
# List projects
ck list

# Check sync status
ck status barnos

# Pull remote context to local
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
```

## How it works

- Markless stores context files under a book/section like `Context/barnos/`.
- Each project maps a local directory to that remote book/section.
- `ck pull` downloads remote files; `ck push` uploads local files.
- Sync compares modification times and picks the newest, backing up the overwritten copy first.

## Cross-device workflow

1. On Linux: edit `~/Projects/barnos/AGENTS.md`, run `ck push barnos`
2. On Windows: open a new PowerShell window and run `ck pull barnos` before a Claude Code session
3. Both agents now see the same context.

### Windows work PC setup

context-keeper runs inside WSL Ubuntu-24.04 on the work PC and stores pulled files at `C:\Users\Rob\Context\<project>\`. A PowerShell profile function lets you run `ck` from any PowerShell window.

If `ck` is not recognized, reload the profile:

```powershell
. $PROFILE
```

Or run it directly via WSL:

```bash
wsl -d Ubuntu-24.04 -u rob /home/rob/.local/bin/ck version
```
