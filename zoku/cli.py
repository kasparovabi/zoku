"""Zoku CLI.

Usage::

    zoku install [--global]     # Install hooks into Claude Code
    zoku uninstall [--global]   # Remove hooks
    zoku setup                  # One-command install (global + welcome)
    zoku patterns               # Show discovered workflow patterns
    zoku traces                 # List recorded session traces
    zoku status                 # Show Zoku status
    zoku analyse                # Force pattern analysis now
    zoku clear                  # Clear all recorded data
"""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from .installer import install, uninstall
from .recorder import load_all_traces, _zoku_dir, _traces_dir
from .detector import detect_patterns, save_patterns, load_patterns

_CMD = "python -m zoku" if platform.system() == "Windows" else "zoku"


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def cmd_setup(args: argparse.Namespace) -> int:
    """One-command setup: install hooks globally and print welcome."""
    _print()
    _print("  Zoku \u2014 invisible automation layer for Claude Code")
    _print("  " + "=" * 50)
    _print()
    actions = install(global_install=True)
    for a in actions:
        _print(f"  {a}")
    _print()
    _print("  Done! Zoku is now active in ALL your projects.")
    _print()
    _print("  What happens next:")
    _print("    - Zoku silently records your tool usage across sessions")
    _print("    - After 2+ sessions, it detects repeated workflow patterns")
    _print("    - Patterns are injected into Claude's context automatically")
    _print()
    _print("  You don't need to do anything \u2014 just use Claude Code normally.")
    _print()
    _print("  Useful commands:")
    _print(f"    {_CMD} status      Show installation status")
    _print(f"    {_CMD} patterns    View discovered workflow patterns")
    _print(f"    {_CMD} traces      List recorded session traces")
    _print(f"    {_CMD} uninstall   Remove Zoku hooks")
    _print()
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    is_global = getattr(args, "global_install", False)
    project_dir = args.project_dir or "."

    if is_global:
        _print("Installing Zoku hooks GLOBALLY (all projects)...")
    else:
        _print("Installing Zoku hooks into Claude Code...")
    _print()
    actions = install(project_dir, global_install=is_global)
    for a in actions:
        _print(f"  {a}")
    _print()
    _print("Zoku is now active.")
    _print("It will silently record your actions and discover workflow patterns.")
    _print()
    _print("You don't need to do anything \u2014 just use Claude Code normally.")
    _print(f"After a few sessions, run: {_CMD} patterns")
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
        _print("Keep using Claude Code \u2014 Zoku will detect patterns after 2+ sessions.")
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


def _check_installed(settings_path: Path) -> bool:
    """Check if Zoku hooks are installed in a settings.json file."""
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        for entries in hooks.values():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    if "zoku" in hook.get("command", "").lower():
                        return True
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return False


def cmd_status(args: argparse.Namespace) -> int:
    project_dir = args.project_dir or "."
    zoku_dir = _zoku_dir(project_dir)

    # Check both local and global settings
    local_settings = Path(project_dir).resolve() / ".claude" / "settings.json"
    global_settings = Path.home() / ".claude" / "settings.json"

    local_installed = _check_installed(local_settings)
    global_installed = _check_installed(global_settings)
    installed = local_installed or global_installed

    if local_installed:
        scope = "project"
    elif global_installed:
        scope = "global"
    else:
        scope = ""

    traces = load_all_traces(project_dir)
    patterns = load_patterns(project_dir)
    total_actions = sum(len(t.actions) for t in traces)

    _print("Zoku Status")
    _print("=" * 40)
    install_str = f"Yes ({scope})" if installed else "No"
    _print(f"  Installed:     {install_str}")
    _print(f"  Data dir:      {zoku_dir}")
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
    zoku_dir = _zoku_dir(project_dir)

    if not zoku_dir.is_dir():
        _print("No Zoku data found.")
        return 0

    import shutil
    traces_dir = zoku_dir / "traces"
    if traces_dir.is_dir():
        count = len(list(traces_dir.glob("*.jsonl")))
        shutil.rmtree(traces_dir)
        _print(f"Cleared {count} session trace(s).")

    patterns_file = zoku_dir / "patterns.json"
    if patterns_file.is_file():
        patterns_file.unlink()
        _print("Cleared saved patterns.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zoku",
        description="Zoku \u2014 invisible automation layer for Claude Code",
    )
    sub = parser.add_subparsers(dest="command")

    # setup command (no extra args needed)
    sub.add_parser("setup", help="One-command global install with welcome guide")

    for name, help_text in [
        ("install", "Install Zoku hooks into Claude Code"),
        ("uninstall", "Remove Zoku hooks"),
        ("patterns", "Show discovered workflow patterns"),
        ("traces", "List recorded session traces"),
        ("status", "Show Zoku status"),
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
        "setup": cmd_setup,
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
