# Zoku

[![CI](https://github.com/kasparovabi/deja/actions/workflows/ci.yml/badge.svg)](https://github.com/kasparovabi/deja/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![No Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#technical-details)

**The invisible automation layer for Claude Code.**

<p align="center">
  <img src="assets/demo.gif" alt="Zoku Demo" width="700">
</p>

Zoku is an open source Claude Code hook that runs silently in the background while you work. It watches every action you take across sessions, discovers repeated patterns in your workflow, and tells you about them so you can automate the boring parts.

You don't configure anything. You don't change how you work. You just install it once and forget about it. Zoku does the rest.

## The Problem

Every developer has habits they don't notice. You grep for something, open the file, edit it, run the tests, then fix the lint errors. You do this ten times a day without thinking about it. Multiply that across weeks and you're spending hours on sequences that could be a single command.

The issue is that nobody sits down and audits their own workflow. It's tedious, it's invisible, and honestly most people don't even realize they're repeating themselves.

## What Zoku Does

Zoku hooks into Claude Code's event system and records every tool action: file reads, edits, searches, bash commands, everything. It stores these as session traces. When a session ends, Zoku runs a pattern detection algorithm across all your recorded sessions. It looks for contiguous subsequences of tool usage that appear in two or more sessions.

When you start a new session, Zoku loads the patterns it found and injects them into Claude's context. Claude now knows "hey, this user frequently does Grep then Read then Edit then Bash then Bash" and can proactively suggest or execute that workflow.

### How the Detection Works

1. Every `PostToolUse` event is recorded as an `Action` with the tool name, a short input summary, timestamp, and session ID
2. Actions within a session form a `SessionTrace`, which is essentially an ordered list of tool names
3. The detector extracts all contiguous subsequences of length 3 to 15 from each session
4. It counts how many *distinct* sessions each subsequence appears in
5. Subsequences that appear in 2+ sessions become candidate patterns
6. Strict subsets of longer patterns are removed (if "A B C" is always part of "A B C D", only the longer one survives)
7. Results are sorted by frequency first, then by length

No machine learning, no cloud calls, no external dependencies. Pure algorithmic analysis using Python's standard library.

### What Gets Stored

All data lives in a `.zoku/` directory (local or global depending on your install):

```
.zoku/
    traces/
        2026-04-01_session123.jsonl    # one JSONL file per session
        2026-04-02_session456.jsonl
    patterns.json                       # discovered workflow patterns
```

Each line in a trace file is a JSON object:

```json
{"tool": "Grep", "input_summary": "grep:TODO", "timestamp": "2026-04-01T14:30:00+00:00", "session_id": "abc123", "success": true}
{"tool": "Read", "input_summary": "/src/main.py", "timestamp": "2026-04-01T14:30:05+00:00", "session_id": "abc123", "success": true}
{"tool": "Edit", "input_summary": "edit:/src/main.py", "timestamp": "2026-04-01T14:30:15+00:00", "session_id": "abc123", "success": true}
```

Nothing sensitive is stored. Input summaries are truncated to 200 characters and only contain file paths or command previews, never file contents.

## Installation

### Quick Install (Recommended)

```bash
pip install zoku && zoku setup
```

That's it. Two commands, zero configuration. Zoku installs globally and works in every project.

### Install from Claude Code

Already inside a Claude Code session? Just ask Claude:

> Install zoku for me: `pip install zoku && zoku setup`

Claude will run it and Zoku starts working immediately — in that session and every future one.

### Install from GitHub (latest development version)

```bash
pip install git+https://github.com/kasparovabi/deja.git && zoku setup
```

### Per-Project Install

If you only want Zoku active in a specific project:

```bash
pip install zoku
cd your-project
zoku install
```

This writes to `your-project/.claude/settings.json` and creates `your-project/.zoku/`.

### Windows

Zoku automatically detects Windows and uses the correct Python path in hook commands. No manual configuration needed.

### Uninstalling

```bash
zoku uninstall --global    # remove global hooks
zoku uninstall             # remove project hooks
zoku clear                 # delete all recorded data
pip uninstall zoku         # remove the package
```

## Usage

There is no usage. That's the point.

Install it and use Claude Code exactly as you always do. Zoku is completely invisible during your sessions. It only surfaces information when:

1. A session **ends** and new patterns are found (logged silently)
2. A session **starts** and previously discovered patterns exist (injected as context for Claude)

### CLI Commands

To inspect what Zoku has learned:

```bash
zoku status      # installation status, session count, pattern count
zoku patterns    # list all discovered workflow patterns with details
zoku traces      # show recorded sessions and their tool sequences
zoku analyse     # force pattern analysis right now (normally happens on session end)
zoku clear       # wipe all traces and patterns
```

### Example Output

After a few sessions, `zoku patterns` might show:

```
Discovered 3 workflow pattern(s):

  Pattern 1: Grep > Read > Edit > Bash > Bash
    Steps:    Grep -> Read -> Edit -> Bash -> Bash
    Seen in:  4 sessions
    Example:
      1. [Grep] grep:handleSubmit
      2. [Read] /src/components/Form.tsx
      3. [Edit] edit:/src/components/Form.tsx
      4. [Bash] npm test
      5. [Bash] npm run lint

  Pattern 2: Read > Edit > Read > Edit
    Steps:    Read -> Edit -> Read -> Edit
    Seen in:  3 sessions

  Pattern 3: Glob > Read > Edit > Bash
    Steps:    Glob -> Read -> Edit -> Bash
    Seen in:  2 sessions
```

## Architecture

```
zoku/
    __init__.py         # package metadata (version 0.1.0)
    __main__.py         # entry point: zoku
    cli.py              # 8 CLI commands (setup, install, uninstall, patterns, traces, status, analyse, clear)
    recorder.py         # Action/SessionTrace dataclasses, JSONL storage, summarise_input()
    detector.py         # Pattern detection: subsequence extraction, frequency counting, subset pruning
    hooks.py            # Claude Code hook handlers (PostToolUse, Stop, SessionStart)
    installer.py        # Hook registration into .claude/settings.json (local + global)
```

### Hook Integration

Zoku registers three hooks in Claude Code's settings:

| Event | What Zoku Does | Timeout |
|-------|---------------|---------|
| `PostToolUse` | Records the action to the session's JSONL trace file | 5s |
| `Stop` | Loads all traces, runs pattern detection, saves new patterns | 15s |
| `SessionStart` | Loads saved patterns and injects them as context for Claude | 5s |

Hooks communicate via stdin/stdout JSON, following Claude Code's hook protocol. Exit code 0 means success (parse the JSON output), exit code 2 means blocking error.

## Technical Details

**Python Version**: 3.10+

**External Dependencies**: None. Everything uses Python's standard library (json, pathlib, dataclasses, argparse, datetime, shutil).

**Test Suite**: 49 tests covering all Zoku functionality. Run with:

```bash
python -m pytest tests/ -v
```

**Data Safety**: Zoku never modifies your code, never sends data anywhere, and never interferes with Claude Code's normal operation. It only *reads* hook events and *writes* to its own `.zoku/` directory.

## Roadmap

This project is part of a larger vision for AI coding tool infrastructure:

**Zoku v2**: Workflow replay (not just detection, but execution), cross project pattern aggregation, pattern sharing between team members

**AgentBlackBox**: SaaS audit trail for AI agent sessions. Full token cost tracking, decision tree visualization, compliance reporting for enterprises that need to prove what their AI agents did and why.

**MirrorMode**: Cross agent workflow translation. Record a workflow in Claude Code, replay it in Cursor or Aider. Universal session format that works across all AI coding tools.

## Contributing

This project is in active development. If you're interested in contributing, the codebase is intentionally simple and well tested. Every module is under 200 lines and uses no external dependencies.

## License

MIT
