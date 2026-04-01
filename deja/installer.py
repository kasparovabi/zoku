"""Deja installer for Claude Code hooks."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path


def _python_command() -> str:
    """Return the correct python command for the current platform.

    On Windows ``python3`` usually doesn't exist — ``python`` is the
    standard command.  On macOS / Linux both work but ``python3`` is
    the safer default.
    """
    if platform.system() == "Windows":
        return "python"
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
                            "command": f"{py} -m deja.hooks post-tool-use",
                            "timeout": 5,
                            "statusMessage": "Deja: recording..."
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
                            "command": f"{py} -m deja.hooks stop",
                            "timeout": 15,
                            "statusMessage": "Deja: analysing patterns..."
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
                            "command": f"{py} -m deja.hooks session-start",
                            "timeout": 5,
                            "statusMessage": "Deja: loading workflows..."
                        }
                    ]
                }
            ],
        }
    }


# Keep module-level constant for backwards compatibility / tests
HOOK_SETTINGS = _build_hook_settings()


def _is_deja_entry(entry: dict) -> bool:
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "deja" in cmd.lower():
            return True
        status = hook.get("statusMessage", "")
        if "Deja" in status:
            return True
    return False


def _global_settings_path() -> Path:
    """Return the path to Claude Code's global (user-level) settings.

    - Linux / macOS: ``~/.claude/settings.json``
    - Windows:       ``%USERPROFILE%\\.claude\\settings.json``
    """
    home = Path.home()
    return home / ".claude" / "settings.json"


def _global_deja_dir() -> Path:
    """Return the global Deja data directory.

    - Linux / macOS: ``~/.deja/``
    - Windows:       ``%USERPROFILE%\\.deja\\``
    """
    return Path.home() / ".deja"


def install(project_dir: str | Path = ".", *, global_install: bool = False) -> list[str]:
    """Install Deja hooks into Claude Code settings.

    Parameters
    ----------
    project_dir:
        The project directory for a local (per-project) install.
    global_install:
        If ``True``, install into the user's global Claude Code settings
        (``~/.claude/settings.json``) so hooks are active in *every*
        project without per-project setup.
    """
    actions: list[str] = []
    hook_settings = _build_hook_settings()

    if global_install:
        settings_path = _global_settings_path()
        deja_dir = _global_deja_dir()
    else:
        root = Path(project_dir).resolve()
        settings_path = root / ".claude" / "settings.json"
        deja_dir = root / ".deja"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Create .deja dir
    deja_dir.mkdir(parents=True, exist_ok=True)
    (deja_dir / "traces").mkdir(exist_ok=True)
    actions.append(f"Created {deja_dir}")

    # Merge into settings.json
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
            cleaned = [e for e in existing_hooks[event_name] if not _is_deja_entry(e)]
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
    """Remove Deja hooks from Claude Code settings."""
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
        remaining = [e for e in entries if not _is_deja_entry(e)]
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
