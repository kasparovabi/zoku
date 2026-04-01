"""HarnessKit policy enforcer — the brain behind the hooks.

This module loads a ``.harnesskit.json`` config and makes permission
decisions for Claude Code hook events.  The shell hook scripts delegate
to this module so that all logic lives in Python.

Usage from hook scripts::

    echo "$INPUT" | python -m harnesskit.hooks.enforcer pre-tool-use
    echo "$INPUT" | python -m harnesskit.hooks.enforcer post-tool-use
    echo "$INPUT" | python -m harnesskit.hooks.enforcer session-start
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..permissions import PermissionPolicy, PermissionRule
from ..security import contains_shell_injection, scan_for_secrets

# ---------------------------------------------------------------------------
# Tool name mapping: Claude Code uses short names, HarnessKit uses full names
# ---------------------------------------------------------------------------

_CLAUDE_TO_HARNESSKIT: dict[str, str] = {
    "Bash": "BashTool",
    "Read": "FileReadTool",
    "Edit": "FileEditTool",
    "Write": "FileWriteTool",
    "Glob": "GlobTool",
    "Grep": "GrepTool",
    "Agent": "AgentTool",
    "WebFetch": "WebFetchTool",
    "WebSearch": "WebSearchTool",
    "NotebookEdit": "NotebookEditTool",
    "TodoWrite": "TodoTool",
    "ToolSearch": "ToolSearch",
}


def _resolve_tool_name(name: str) -> list[str]:
    """Return candidate names to check against the policy.

    Claude Code sends short names like ``Bash``, but HarnessKit policies
    may use either ``Bash`` or ``BashTool``.  We check both.
    """
    candidates = [name]
    mapped = _CLAUDE_TO_HARNESSKIT.get(name)
    if mapped and mapped != name:
        candidates.append(mapped)
    # Also try the reverse: if someone passes BashTool, check Bash too
    for short, full in _CLAUDE_TO_HARNESSKIT.items():
        if full == name and short not in candidates:
            candidates.append(short)
    return candidates

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG_FILENAMES = (
    ".harnesskit.json",
    "harnesskit.json",
)


def find_config(cwd: str | None = None) -> Path | None:
    """Walk up from *cwd* looking for a HarnessKit config file."""
    start = Path(cwd) if cwd else Path.cwd()
    current = start.resolve()
    for _ in range(20):  # safety limit
        for name in _CONFIG_FILENAMES:
            candidate = current / name
            if candidate.is_file():
                return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def load_policy_from_config(config_path: Path) -> PermissionPolicy:
    """Load a ``PermissionPolicy`` from a HarnessKit JSON config."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    perm_data = data.get("permissions", {})
    rules = []
    for r in perm_data.get("rules", []):
        rules.append(PermissionRule(
            target=r.get("target", ""),
            action=r.get("action", "deny"),
            reason=r.get("reason", ""),
        ))
    return PermissionPolicy(
        rules=tuple(rules),
        default_action=perm_data.get("default_action", "deny"),
    )


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

_LOG_DIR_ENV = "HARNESSKIT_LOG_DIR"


def _log_dir() -> Path:
    """Return the audit log directory, creating it if needed."""
    env = os.environ.get(_LOG_DIR_ENV)
    if env:
        d = Path(env)
    else:
        d = Path.cwd() / ".claude" / "harnesskit-logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_audit_log(event: dict) -> None:
    """Append *event* as a JSON line to today's audit log."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = _log_dir() / f"audit-{today}.jsonl"
    line = json.dumps(event, ensure_ascii=False)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# PreToolUse handler
# ---------------------------------------------------------------------------

@dataclass
class PreToolUseResult:
    decision: str  # "allow", "deny", "ask"
    reason: str = ""
    updated_input: dict | None = None
    context: str = ""

    def to_hook_output(self) -> dict:
        out: dict[str, Any] = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": self.decision,
            }
        }
        if self.reason:
            out["hookSpecificOutput"]["permissionDecisionReason"] = self.reason
        if self.updated_input is not None:
            out["hookSpecificOutput"]["updatedInput"] = self.updated_input
        if self.context:
            out["hookSpecificOutput"]["additionalContext"] = self.context
        return out


def handle_pre_tool_use(event: dict) -> PreToolUseResult:
    """Evaluate a PreToolUse event against the HarnessKit policy."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    cwd = event.get("cwd")

    # 1. Find and load config
    config_path = find_config(cwd)
    if config_path is None:
        # No config = no enforcement, passthrough
        return PreToolUseResult(decision="allow", context="No HarnessKit config found")

    policy = load_policy_from_config(config_path)

    # 2. Check permission policy (try both Claude Code and HarnessKit names)
    action, reason = "deny", "No matching rule"
    for candidate in _resolve_tool_name(tool_name):
        candidate_action, candidate_reason = policy.evaluate(candidate)
        if candidate_action == "allow":
            action, reason = candidate_action, candidate_reason
            break
        action, reason = candidate_action, candidate_reason

    if action == "deny":
        _write_audit_log({
            "event": "PreToolUse",
            "tool": tool_name,
            "decision": "deny",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return PreToolUseResult(
            decision="deny",
            reason=f"[HarnessKit] {reason}",
        )

    # 3. Safety checks on tool input
    # 3a. Shell injection detection for Bash commands
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        # Check for known dangerous patterns
        dangerous_patterns = [
            ("rm -rf /", "Recursive deletion of root filesystem"),
            ("rm -rf ~", "Recursive deletion of home directory"),
            (":(){:|:&};:", "Fork bomb detected"),
            ("mkfs.", "Filesystem format command detected"),
            ("dd if=/dev/zero", "Disk overwrite detected"),
            ("> /dev/sda", "Direct disk write detected"),
            ("chmod -R 777 /", "Recursive world-writable permission on root"),
        ]
        for pattern, desc in dangerous_patterns:
            if pattern in command:
                _write_audit_log({
                    "event": "PreToolUse",
                    "tool": tool_name,
                    "command": command[:200],
                    "decision": "deny",
                    "reason": desc,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return PreToolUseResult(
                    decision="deny",
                    reason=f"[HarnessKit] Dangerous command blocked: {desc}",
                )

    # 3b. Secret detection in file write content
    if tool_name in ("Write", "FileWriteTool", "Edit", "FileEditTool"):
        content_fields = ("file_contents", "content", "new_string")
        for field_name in content_fields:
            content = tool_input.get(field_name, "")
            if content and isinstance(content, str):
                secrets = scan_for_secrets({"content": content})
                if secrets:
                    secret_types = ", ".join(s.pattern_name for s in secrets[:3])
                    _write_audit_log({
                        "event": "PreToolUse",
                        "tool": tool_name,
                        "decision": "deny",
                        "reason": f"Potential secrets detected: {secret_types}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    return PreToolUseResult(
                        decision="deny",
                        reason=f"[HarnessKit] Blocked: potential secrets in file content ({secret_types}). "
                               "Remove secrets before writing.",
                    )

    # 3c. Protected file patterns
    protected_patterns = (".env", ".secrets", "credentials", "id_rsa", ".pem")
    file_path = tool_input.get("file_path", "")
    if file_path:
        for pattern in protected_patterns:
            if pattern in file_path.lower():
                _write_audit_log({
                    "event": "PreToolUse",
                    "tool": tool_name,
                    "file": file_path,
                    "decision": "ask",
                    "reason": f"Protected file pattern: {pattern}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                return PreToolUseResult(
                    decision="ask",
                    reason=f"[HarnessKit] File matches protected pattern '{pattern}'. Requesting user confirmation.",
                )

    # 4. Log and allow
    _write_audit_log({
        "event": "PreToolUse",
        "tool": tool_name,
        "decision": "allow",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return PreToolUseResult(decision="allow")


# ---------------------------------------------------------------------------
# PostToolUse handler
# ---------------------------------------------------------------------------

@dataclass
class PostToolUseResult:
    decision: str = "allow"  # "allow" or "block"
    reason: str = ""

    def to_hook_output(self) -> dict:
        if self.decision == "block":
            return {"decision": "block", "reason": self.reason}
        return {}


def handle_post_tool_use(event: dict) -> PostToolUseResult:
    """Log and optionally flag PostToolUse events."""
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    # Audit log
    _write_audit_log({
        "event": "PostToolUse",
        "tool": tool_name,
        "input_summary": _summarise(tool_input),
        "result_success": tool_result.get("success", True) if isinstance(tool_result, dict) else True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # Check if result contains leaked secrets
    if isinstance(tool_result, dict):
        result_str = json.dumps(tool_result)
        if len(result_str) < 50000:  # Only scan reasonable sizes
            secrets = scan_for_secrets(tool_result)
            if secrets:
                secret_types = ", ".join(s.pattern_name for s in secrets[:3])
                return PostToolUseResult(
                    decision="block",
                    reason=f"[HarnessKit] Tool result contains potential secrets ({secret_types}). "
                           "Review before proceeding.",
                )

    return PostToolUseResult(decision="allow")


# ---------------------------------------------------------------------------
# SessionStart handler
# ---------------------------------------------------------------------------

def handle_session_start(event: dict) -> dict:
    """Log session start and return context for Claude."""
    cwd = event.get("cwd")
    config_path = find_config(cwd)

    _write_audit_log({
        "event": "SessionStart",
        "config_found": config_path is not None,
        "config_path": str(config_path) if config_path else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if config_path is None:
        return {}

    # Load config and provide context
    data = json.loads(config_path.read_text(encoding="utf-8"))
    project_name = data.get("project_name", "unknown")
    tools = data.get("tools", [])
    perm_data = data.get("permissions", {})
    default_action = perm_data.get("default_action", "deny")

    context = (
        f"[HarnessKit] Project: {project_name} | "
        f"Tools: {len(tools)} configured | "
        f"Default policy: {default_action}"
    )

    return {"additionalContext": context}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarise(data: dict, max_len: int = 100) -> str:
    """Short string summary of a dict for logging."""
    s = json.dumps(data, ensure_ascii=False)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Read hook event from stdin, process, write response to stdout."""
    if len(sys.argv) < 2:
        print("Usage: python -m harnesskit.hooks.enforcer <pre-tool-use|post-tool-use|session-start>",
              file=sys.stderr)
        sys.exit(1)

    handler_name = sys.argv[1]

    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        event = {}

    if handler_name == "pre-tool-use":
        result = handle_pre_tool_use(event)
        output = result.to_hook_output()
    elif handler_name == "post-tool-use":
        result = handle_post_tool_use(event)
        output = result.to_hook_output()
    elif handler_name == "session-start":
        output = handle_session_start(event)
    else:
        print(f"Unknown handler: {handler_name}", file=sys.stderr)
        sys.exit(1)

    if output:
        print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
