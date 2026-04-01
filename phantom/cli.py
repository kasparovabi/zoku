"""Phantom Agent CLI.

Usage::

    python -m phantom install              # Install hooks into Claude Code
    python -m phantom uninstall            # Remove hooks
    python -m phantom patterns             # Show discovered workflow patterns
    python -m phantom traces               # List recorded session traces
    python -m phantom status               # Show Phantom Agent status
    python -m phantom analyse              # Force pattern analysis now
    python -m phantom clear                # Clear all recorded data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .installer import install, uninstall
from .recorder import load_all_traces, _phantom_dir, _traces_dir
from .detector import detect_patterns, save_patterns, load_patterns


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def cmd_install(args: argparse.Namespace) -> int:
    is_global = getattr(args, "global_install", False)
    project_dir = args.project_dir or "."

    if is_global:
        _print("Installing Phantom Agent hooks GLOBALLY (all projects)...")
    else:
        _print("Installing Phantom Agent hooks into Claude Code...")
    _print()
    actions = install(project_dir, global_install=is_global)
    for a in actions:
        _print(f"  {a}")
    _print()
    _print("Phantom Agent is now active.")
    _print("It will silently record your actions and discover workflow patterns.")
    _print()
    _print("You don't need to do anything — just use Claude Code normally.")
    _print("After a few sessions, run: python -m phantom patterns")
    if not is_global:
        _print()
        _print("Tip: Use --global to install once for ALL projects.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    is_global = getattr(args, "global_install", False)
    project_dir = args.project_dir or "."
    actions = uninstall(project_dir, global_install=is_global)
    for a in actions:
        _print(f"  {a}")
    return 0


def cmd_patterns(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    patterns = load_patterns(project_dir)

    if not patterns:
        _print("No workflow patterns discovered yet.")
        _print("Keep using Claude Code — Phantom will detect patterns after 2+ sessions.")
        return 0

    _print(f"Discovered {len(patterns)} workflow pattern(s):")
    _print()

    for i, p in enumerate(patterns, 1):
        _print(f"  Pattern {i}: {p.name}")
        _print(f"    Steps:    {' -> '.join(p.steps)}")
        _print(f"    Seen in:  {p.occurrence_count} sessions")
        if p.example_inputs:
            _print(f"    Example:")
            for j, (step, inp) in enumerate(zip(p.steps, p.example_inputs)):
                if inp:
                    _print(f"      {j+1}. [{step}] {inp}")
        _print()
    return 0


def cmd_traces(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    traces = load_all_traces(project_dir)

    if not traces:
        _print("No session traces recorded yet.")
        return 0

    _print(f"Recorded {len(traces)} session trace(s):")
    _print()

    for trace in traces:
        seq = trace.tool_sequence
        _print(f"  Session: {trace.session_id}")
        _print(f"    Actions: {len(trace.actions)}")
        if seq:
            preview = " -> ".join(seq[:8])
            if len(seq) > 8:
                preview += f" ... (+{len(seq) - 8} more)"
            _print(f"    Flow:    {preview}")
        _print()
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    phantom_dir = _phantom_dir(project_dir)
    settings_path = Path(project_dir).resolve() / ".claude" / "settings.json"

    # Check installation
    installed = False
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            hooks = data.get("hooks", {})
            for entries in hooks.values():
                for entry in entries:
                    for hook in entry.get("hooks", []):
                        if "phantom" in hook.get("command", "").lower():
                            installed = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    traces = load_all_traces(project_dir)
    patterns = load_patterns(project_dir)
    total_actions = sum(len(t.actions) for t in traces)

    _print("Phantom Agent Status")
    _print("=" * 40)
    _print(f"  Installed:     {'Yes' if installed else 'No'}")
    _print(f"  Data dir:      {phantom_dir}")
    _print(f"  Sessions:      {len(traces)}")
    _print(f"  Total actions: {total_actions}")
    _print(f"  Patterns:      {len(patterns)}")
    if patterns:
        _print()
        _print("  Top patterns:")
        for p in patterns[:3]:
            _print(f"    - {p.name} ({p.occurrence_count}x)")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    traces = load_all_traces(project_dir)

    if len(traces) < 2:
        _print(f"Only {len(traces)} session(s) recorded. Need at least 2 to find patterns.")
        return 0

    _print(f"Analysing {len(traces)} sessions...")
    patterns = detect_patterns(traces, cwd=project_dir)
    save_patterns(patterns, cwd=project_dir)

    if not patterns:
        _print("No repeating patterns found yet. Keep using Claude Code!")
        return 0

    _print(f"Found {len(patterns)} pattern(s):")
    _print()
    for i, p in enumerate(patterns, 1):
        _print(f"  {i}. {p.name} ({p.occurrence_count}x, {p.length} steps)")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    phantom_dir = _phantom_dir(project_dir)

    if not phantom_dir.is_dir():
        _print("No Phantom data found.")
        return 0

    import shutil
    traces_dir = phantom_dir / "traces"
    if traces_dir.is_dir():
        count = len(list(traces_dir.glob("*.jsonl")))
        shutil.rmtree(traces_dir)
        _print(f"Cleared {count} session trace(s).")

    patterns_file = phantom_dir / "patterns.json"
    if patterns_file.is_file():
        patterns_file.unlink()
        _print("Cleared saved patterns.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phantom",
        description="Phantom Agent — invisible automation layer for Claude Code",
    )
    sub = parser.add_subparsers(dest="command")

    for name, help_text in [
        ("install", "Install Phantom Agent hooks into Claude Code"),
        ("uninstall", "Remove Phantom Agent hooks"),
        ("patterns", "Show discovered workflow patterns"),
        ("traces", "List recorded session traces"),
        ("status", "Show Phantom Agent status"),
        ("analyse", "Force pattern analysis now"),
        ("clear", "Clear all recorded data"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("-p", "--project-dir", help="Project directory (default: cwd)")
        if name in ("install", "uninstall"):
            p.add_argument(
                "-g", "--global",
                dest="global_install",
                action="store_true",
                default=False,
                help="Install/uninstall globally (~/.claude/settings.json) for all projects",
            )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "patterns": cmd_patterns,
        "traces": cmd_traces,
        "status": cmd_status,
        "analyse": cmd_analyse,
        "clear": cmd_clear,
    }

    if args.command in handlers:
        return handlers[args.command](args)

    parser.print_help()
    return 0
