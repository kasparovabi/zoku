"""Zoku hook handlers for Claude Code.

Hooks run at different points in the Claude Code lifecycle:

- **PostToolUse** — records every tool action to the session trace
- **Stop** — when Claude finishes, analyses all traces for patterns
- **SessionStart** — loads discovered patterns and injects context
- **UserPromptSubmit** — records user prompts for intent→action correlation

Usage from shell scripts::

    echo "$INPUT" | python -m zoku.hooks post-tool-use
    echo "$INPUT" | python -m zoku.hooks stop
    echo "$INPUT" | python -m zoku.hooks session-start
    echo "$INPUT" | python -m zoku.hooks user-prompt-submit
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from .recorder import record_action, record_prompt, load_all_traces
from .detector import detect_patterns, save_patterns, load_patterns


def handle_post_tool_use(event: dict) -> dict:
    """Record the tool action. Returns empty dict (passthrough)."""
    cwd = event.get("cwd")
    record_action(event, cwd=cwd)
    return {}


def handle_stop(event: dict) -> dict:
    """Analyse all recorded traces and report new patterns."""
    cwd = event.get("cwd")
    if event.get("stop_hook_active"):
        return {}
    traces = load_all_traces(cwd)
    if len(traces) < 2:
        return {}
    patterns = detect_patterns(traces, cwd=cwd)
    if not patterns:
        return {}
    old_patterns = load_patterns(cwd)
    old_names = {p.name for p in old_patterns}
    new_patterns = [p for p in patterns if p.name not in old_names]
    save_patterns(patterns, cwd)
    if not new_patterns:
        return {}
    lines = ["[Zoku] New workflow patterns discovered:", ""]
    for i, p in enumerate(new_patterns[:5], 1):
        lines.append(f"  {i}. {p.name}")
        lines.append(f"     Seen in {p.occurrence_count} sessions, {p.length} steps")
        if p.example_inputs:
            examples = [e for e in p.example_inputs[:3] if e]
            if examples:
                lines.append(f"     Example: {' -> '.join(examples)}")
        lines.append("")
    lines.append("Run `python -m zoku patterns` to see all discovered workflows.")
    return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "\n".join(lines)}}


def handle_session_start(event: dict) -> dict:
    """Load saved patterns and inject a summary into Claude's context."""
    cwd = event.get("cwd")
    source = event.get("source", "startup")
    patterns = load_patterns(cwd)
    if not patterns:
        return {}
    if source == "compact":
        prefix = f"[Zoku] Re-injecting {len(patterns)} workflow pattern(s) after context compaction:"
    else:
        prefix = f"[Zoku] {len(patterns)} workflow pattern(s) detected from your previous sessions:"
    lines = [prefix, ""]
    for i, p in enumerate(patterns[:5], 1):
        lines.append(f"  {i}. {p.name} ({p.occurrence_count}x)")
    if len(patterns) > 5:
        lines.append(f"  ... and {len(patterns) - 5} more")
    lines.append("")
    lines.append("Tip: These are actions you repeat often. Consider automating them.")
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}


def handle_user_prompt_submit(event: dict) -> dict:
    """Record the user's prompt for intent\u2192action correlation."""
    cwd = event.get("cwd")
    record_prompt(event, cwd=cwd)
    return {}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m zoku.hooks <post-tool-use|stop|session-start|user-prompt-submit>", file=sys.stderr)
        sys.exit(1)
    handler_name = sys.argv[1]
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {}
    handlers = {
        "post-tool-use": handle_post_tool_use,
        "stop": handle_stop,
        "session-start": handle_session_start,
        "user-prompt-submit": handle_user_prompt_submit,
    }
    handler = handlers.get(handler_name)
    if not handler:
        print(f"Unknown handler: {handler_name}", file=sys.stderr)
        sys.exit(1)
    output = handler(event)
    if output:
        print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
