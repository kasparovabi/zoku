"""Action recorder \u2014 captures every tool action in a session.

Each PostToolUse event is recorded as an ``Action``. Actions within
a session form a ``SessionTrace`` \u2014 the raw material that the pattern
detector analyses.

Storage layout::

    .zoku/
        traces/
            2026-04-01_abc123.jsonl   # one file per session
        patterns.json                  # discovered workflow patterns
        prompts/
            2026-04-01_abc123.jsonl   # user prompts per session
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Action:
    """A single recorded tool action."""
    tool: str
    input_summary: str
    timestamp: str
    session_id: str
    success: bool = True
    response_summary: str = ""
    tool_use_id: str = ""
    agent_id: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v or k in ("tool", "input_summary", "timestamp", "session_id", "success")}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(
            tool=d.get("tool", ""),
            input_summary=d.get("input_summary", ""),
            timestamp=d.get("timestamp", ""),
            session_id=d.get("session_id", ""),
            success=d.get("success", True),
            response_summary=d.get("response_summary", ""),
            tool_use_id=d.get("tool_use_id", ""),
            agent_id=d.get("agent_id", ""),
        )


@dataclass
class SessionTrace:
    """Ordered list of actions within one session."""
    session_id: str
    actions: list[Action] = field(default_factory=list)

    @property
    def tool_sequence(self) -> tuple[str, ...]:
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


_ZOKU_DIR_ENV = "ZOKU_DATA_DIR"


def _zoku_dir(cwd: str | None = None) -> Path:
    env = os.environ.get(_ZOKU_DIR_ENV)
    if env:
        return Path(env)
    base = Path(cwd) if cwd else Path.cwd()
    local = base / ".zoku"
    if local.is_dir():
        return local
    global_dir = Path.home() / ".zoku"
    if global_dir.is_dir():
        return global_dir
    return local


def _traces_dir(cwd: str | None = None) -> Path:
    d = _zoku_dir(cwd) / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prompts_dir(cwd: str | None = None) -> Path:
    d = _zoku_dir(cwd) / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace_path(session_id: str, cwd: str | None = None) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_id = session_id.replace("/", "_").replace("\\", "_")[:64] or "unknown"
    return _traces_dir(cwd) / f"{today}_{safe_id}.jsonl"


def _normalise_tool_name(tool_name: str) -> str:
    """Normalise MCP tool names: mcp__server__tool -> server:tool."""
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) == 3:
            return f"{parts[1]}:{parts[2]}"
    return tool_name


def summarise_input(tool_name: str, tool_input: dict) -> str:
    """Create a short human-readable summary of a tool's input."""
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
    if tool_name.startswith("mcp__"):
        readable = _normalise_tool_name(tool_name)
        for key in ("owner", "repo", "path", "query", "body", "url"):
            if key in tool_input:
                return f"{readable}:{tool_input[key]}"[:200]
        keys = list(tool_input.keys())[:3]
        return f"{readable}({', '.join(keys)})"[:200]
    keys = list(tool_input.keys())[:3]
    return f"{tool_name}({', '.join(keys)})"[:200]


def summarise_response(tool_name: str, tool_response: Any) -> str:
    """Create a short summary of a tool's response."""
    if not tool_response:
        return ""
    if isinstance(tool_response, str):
        return tool_response[:100]
    if isinstance(tool_response, dict):
        if "exitCode" in tool_response:
            code = tool_response["exitCode"]
            if code != 0:
                stderr = tool_response.get("stderr", "")[:80]
                return f"exit:{code} {stderr}".strip()[:100]
            return "exit:0"
        if "success" in tool_response:
            return "ok" if tool_response["success"] else "failed"
        keys = list(tool_response.keys())[:3]
        return f"({', '.join(keys)})"[:100]
    return ""


def record_action(event: dict, cwd: str | None = None) -> Action:
    """Record a PostToolUse event to disk and return the Action."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    session_id = event.get("session_id", "unknown")
    tool_response = event.get("tool_response", {})
    tool_use_id = event.get("tool_use_id", "")
    agent_id = event.get("agent_id", "")

    success = True
    if isinstance(tool_response, dict):
        success = tool_response.get("success", True)
        if "exitCode" in tool_response:
            success = tool_response["exitCode"] == 0

    action = Action(
        tool=_normalise_tool_name(tool_name),
        input_summary=summarise_input(tool_name, tool_input),
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        success=success,
        response_summary=summarise_response(tool_name, tool_response),
        tool_use_id=tool_use_id,
        agent_id=agent_id,
    )

    path = _trace_path(session_id, cwd)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(action.to_dict(), ensure_ascii=False) + "\n")

    return action


def record_prompt(event: dict, cwd: str | None = None) -> None:
    """Record a UserPromptSubmit event to disk."""
    session_id = event.get("session_id", "unknown")
    prompt = event.get("prompt", "")
    if not prompt:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_id = session_id.replace("/", "_").replace("\\", "_")[:64] or "unknown"
    path = _prompts_dir(cwd) / f"{today}_{safe_id}.jsonl"
    entry = {
        "prompt": prompt[:500],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_trace(session_id: str, cwd: str | None = None) -> SessionTrace | None:
    path = _trace_path(session_id, cwd)
    if not path.is_file():
        return None
    return SessionTrace.from_jsonl(path.read_text(encoding="utf-8"), session_id)


def load_all_traces(cwd: str | None = None) -> list[SessionTrace]:
    traces_dir = _traces_dir(cwd)
    traces = []
    for path in sorted(traces_dir.glob("*.jsonl")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            traces.append(SessionTrace.from_jsonl(text))
    return traces
