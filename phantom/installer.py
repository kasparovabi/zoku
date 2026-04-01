"""Phantom Agent installer for Claude Code hooks."""

from __future__ import annotations

import json
import stat
from pathlib import Path


HOOK_SETTINGS = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -m phantom.hooks post-tool-use",
                        "timeout": 5,
                        "statusMessage": "Phantom: recording..."
                    }
                ]
            }
        ],
        "Stop": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -m phantom.hooks stop",
                        "timeout": 15,
                        "statusMessage": "Phantom: analysing patterns..."
                    }
                ]
            }
        ],
        "SessionStart": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -m phantom.hooks session-start",
                        "timeout": 5,
                        "statusMessage": "Phantom: loading workflows..."
                    }
                ]
            }
        ],
    }
}


def _is_phantom_entry(entry: dict) -> bool:
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "phantom" in cmd.lower():
            return True
        status = hook.get("statusMessage", "")
        if "Phantom" in status:
            return True
    return False


def install(project_dir: str | Path = ".") -> list[str]:
    """Install Phantom Agent hooks into Claude Code settings."""
    root = Path(project_dir).resolve()
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []

    # Create .phantom dir
    phantom_dir = root / ".phantom"
    phantom_dir.mkdir(parents=True, exist_ok=True)
    (phantom_dir / "traces").mkdir(exist_ok=True)
    actions.append(f"Created {phantom_dir}")

    # Merge into settings.json
    existing: dict = {}
    if settings_path.is_file():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = {}

    existing_hooks = existing.get("hooks", {})
    for event_name, entries in HOOK_SETTINGS["hooks"].items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = entries
        else:
            cleaned = [e for e in existing_hooks[event_name] if not _is_phantom_entry(e)]
            cleaned.extend(entries)
            existing_hooks[event_name] = cleaned

    existing["hooks"] = existing_hooks
    settings_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    actions.append(f"Updated {settings_path}")
    return actions


def uninstall(project_dir: str | Path = ".") -> list[str]:
    """Remove Phantom Agent hooks from Claude Code settings."""
    root = Path(project_dir).resolve()
    settings_path = root / ".claude" / "settings.json"
    actions: list[str] = []

    if not settings_path.is_file():
        return ["No settings.json found"]

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ["Could not parse settings.json"]

    hooks = data.get("hooks", {})
    cleaned: dict = {}
    for event_name, entries in hooks.items():
        remaining = [e for e in entries if not _is_phantom_entry(e)]
        if remaining:
            cleaned[event_name] = remaining

    if cleaned:
        data["hooks"] = cleaned
    elif "hooks" in data:
        del data["hooks"]

    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    actions.append(f"Cleaned {settings_path}")
    return actions
