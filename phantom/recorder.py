"""Action recorder — captures every tool action in a session.

Each PostToolUse event is recorded as an ``Action``. Actions within
a session form a ``SessionTrace`` — the raw material that the pattern
detector analyses.

Storage layout::

    .phantom/
        traces/
            2026-04-01_abc123.jsonl   # one file per session
        patterns.json                  # discovered workflow patterns
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """A single recorded tool action."""
    tool: str
    input_summary: str
    timestamp: str
    session_id: str
    success: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(
            tool=d.get("tool", ""),
            input_summary=d.get("input_summary", ""),
            timestamp=d.get("timestamp", ""),
            session_id=d.get("session_id", ""),
            success=d.get("success", True),
        )


@dataclass
class SessionTrace:
    """Ordered list of actions within one session."""
    session_id: str
    actions: list[Action] = field(default_factory=list)

    @property
    def tool_sequence(self) -> tuple[str, ...]:
        """Just the tool names in order — used for pattern matching."""
        return tuple(a.tool for a in self.actions)

    def append(self, action: Action) -> None:
        self.actions.append(action)

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(a.to_dict(), ensure_ascii=False) for a in self.actions)

    @classmethod
    def from_jsonl(cls, text: str, session_id: str = "") -> "SessionTrace":
        actions = []
        for line in text.strip().split("\n"):
            if line.strip():
                actions.append(Action.from_dict(json.loads(line)))
        sid = session_id or (actions[0].session_id if actions else "unknown")
        return cls(session_id=sid, actions=actions)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_PHANTOM_DIR_ENV = "PHANTOM_DATA_DIR"


def _phantom_dir(cwd: str | None = None) -> Path:
    env = os.environ.get(_PHANTOM_DIR_ENV)
    if env:
        return Path(env)
    base = Path(cwd) if cwd else Path.cwd()
    return base / ".phantom"


def _traces_dir(cwd: str | None = None) -> Path:
    d = _phantom_dir(cwd) / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace_path(session_id: str, cwd: str | None = None) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_id = session_id.replace("/", "_").replace("\\", "_")[:64] or "unknown"
    return _traces_dir(cwd) / f"{today}_{safe_id}.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarise_input(tool_name: str, tool_input: dict) -> str:
    """Create a short human-readable summary of a tool's input.

    This is what gets stored — not the full (potentially huge) input.
    """
    if tool_name in ("Bash", "BashTool"):
        cmd = tool_input.get("command", "")
        return cmd[:200] if cmd else "(empty)"

    if tool_name in ("Read", "FileReadTool"):
        return tool_input.get("file_path", "")[:200]

    if tool_name in ("Edit", "FileEditTool"):
        fp = tool_input.get("file_path", "")
        return f"edit:{fp}"[:200]

    if tool_name in ("Write", "FileWriteTool"):
        fp = tool_input.get("file_path", "")
        return f"write:{fp}"[:200]

    if tool_name in ("Glob", "GlobTool"):
        return f"glob:{tool_input.get('pattern', '')}"[:200]

    if tool_name in ("Grep", "GrepTool"):
        return f"grep:{tool_input.get('pattern', '')}"[:200]

    if tool_name in ("Agent", "AgentTool"):
        desc = tool_input.get("description", tool_input.get("prompt", ""))
        return f"agent:{desc}"[:200]

    if tool_name in ("WebSearch", "WebSearchTool"):
        return f"search:{tool_input.get('query', '')}"[:200]

    if tool_name in ("WebFetch", "WebFetchTool"):
        return f"fetch:{tool_input.get('url', '')}"[:200]

    # Generic fallback
    keys = list(tool_input.keys())[:3]
    return f"{tool_name}({', '.join(keys)})"[:200]


def record_action(event: dict, cwd: str | None = None) -> Action:
    """Record a PostToolUse event to disk and return the Action."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("session_id", "unknown")
    tool_result = event.get("tool_result", {})
    success = True
    if isinstance(tool_result, dict):
        success = tool_result.get("success", True)

    action = Action(
        tool=tool_name,
        input_summary=summarise_input(tool_name, tool_input),
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        success=success,
    )

    # Append to trace file
    path = _trace_path(session_id, cwd)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(action.to_dict(), ensure_ascii=False) + "\n")

    return action


def load_trace(session_id: str, cwd: str | None = None) -> SessionTrace | None:
    """Load a specific session trace by ID."""
    path = _trace_path(session_id, cwd)
    if not path.is_file():
        return None
    return SessionTrace.from_jsonl(path.read_text(encoding="utf-8"), session_id)


def load_all_traces(cwd: str | None = None) -> list[SessionTrace]:
    """Load all recorded session traces."""
    traces_dir = _traces_dir(cwd)
    traces = []
    for path in sorted(traces_dir.glob("*.jsonl")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            traces.append(SessionTrace.from_jsonl(text))
    return traces
