"""Zoku installer for Claude Code hooks."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path


def _python_command() -> str:
    """Return the Python command for hook scripts.

    Claude Code runs hook commands in a shell (bash on all platforms,
    including Windows).  Windows-style paths like ``C:\\Python313\\python.exe``
    break in bash, so on Windows we use the plain ``python`` command which
    bash can resolve via PATH.  On macOS/Linux ``sys.executable`` is safe.
    """
    if platform.system() == "Windows":
        return "python"
    exe = sys.executable
    if exe:
        return exe
    return "python3"


def _build_hook_settings() -> dict:
    """Build hook settings with the correct python command."""
    py = _python_command()
    return {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{py} -m zoku.hooks post-tool-use",
                            "timeout": 5,
                            "statusMessage": "Zoku: recording..."
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
                            "command": f"{py} -m zoku.hooks stop",
                            "timeout": 15,
                            "statusMessage": "Zoku: analysing patterns..."
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
                            "command": f"{py} -m zoku.hooks session-start",
                            "timeout": 5,
                            "statusMessage": "Zoku: loading workflows..."
                        }
                    ]
                }
            ],
            "UserPromptSubmit": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{py} -m zoku.hooks user-prompt-submit",
                            "timeout": 3,
                            "statusMessage": "Zoku: logging prompt..."
                        }
                    ]
                }
            ],
        }
    }


HOOK_SETTINGS = _build_hook_settings()


def _is_zoku_entry(entry: dict) -> bool:
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "zoku" in cmd.lower() or "deja" in cmd.lower():
            return True
        status = hook.get("statusMessage", "")
        if "Zoku" in status or "Deja" in status:
            return True
    return False


def _global_settings_path() -> Path:
    home = Path.home()
    return home / ".claude" / "settings.json"


def _global_zoku_dir() -> Path:
    return Path.home() / ".zoku"


def install(project_dir: str | Path = ".", *, global_install: bool = False) -> list[str]:
    """Install Zoku hooks into Claude Code settings."""
    actions: list[str] = []
    hook_settings = _build_hook_settings()

    if global_install:
        settings_path = _global_settings_path()
        zoku_dir = _global_zoku_dir()
    else:
        root = Path(project_dir).resolve()
        settings_path = root / ".claude" / "settings.json"
        zoku_dir = root / ".zoku"

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    zoku_dir.mkdir(parents=True, exist_ok=True)
    (zoku_dir / "traces").mkdir(exist_ok=True)
    actions.append(f"Created {zoku_dir}")

    existing: dict = {}
    if settings_path.is_file():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = {}

    existing_hooks = existing.get("hooks", {})
    for event_name, entries in hook_settings["hooks"].items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = entries
        else:
            cleaned = [e for e in existing_hooks[event_name] if not _is_zoku_entry(e)]
            cleaned.extend(entries)
            existing_hooks[event_name] = cleaned

    existing["hooks"] = existing_hooks
    settings_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    scope = "global (all projects)" if global_install else "project-local"
    actions.append(f"Updated {settings_path} ({scope})")
    return actions


def uninstall(project_dir: str | Path = ".", *, global_install: bool = False) -> list[str]:
    """Remove Zoku hooks from Claude Code settings."""
    if global_install:
        settings_path = _global_settings_path()
    else:
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
        remaining = [e for e in entries if not _is_zoku_entry(e)]
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
    scope = "global" if global_install else "project-local"
    actions.append(f"Cleaned {settings_path} ({scope})")
    return actions
