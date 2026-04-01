# Phantom Agent + HarnessKit

Two open-source tools that extend Claude Code with invisible automation and no-code configuration.

## Phantom Agent

An invisible Claude Code hook that silently watches your actions, detects repeated patterns across sessions, and suggests automating them as workflows.

### How it works

1. **Records** every tool action (file reads, edits, commands) via PostToolUse hook
2. **Analyses** patterns when a session ends via Stop hook
3. **Suggests** discovered workflows when a new session starts via SessionStart hook

### Quick start

```bash
git clone https://github.com/kasparovabi/claw-code.git
cd claw-code
git checkout claude/analyze-repo-content-aZ3OC

# Install globally (works in ALL projects)
python -m phantom install --global

# Or install for current project only
python -m phantom install
```

Then just use Claude Code normally. After 2-3 sessions, check:

```bash
python -m phantom patterns    # See discovered workflows
python -m phantom status      # Overview
python -m phantom traces      # Session history
python -m phantom analyse     # Force analysis now
```

### Windows note

On Windows, Phantom automatically uses `python` instead of `python3`.

## HarnessKit

A no-code agent harness configuration toolkit. Define tool permissions, security policies, and presets — then export native config for Claude Code, Cursor, Aider, or Codex CLI.

```bash
python -m harnesskit bootstrap    # Interactive setup
python -m harnesskit catalog      # Browse available tools
python -m harnesskit adapt        # Export to your CLI tool
```

## Requirements

- Python 3.10+
- Claude Code CLI
- Zero external dependencies (stdlib only)

## Running tests

```bash
python -m pytest tests/ -v
```

## License

MIT
