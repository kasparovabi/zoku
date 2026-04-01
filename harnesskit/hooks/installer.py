"""HarnessKit hook installer for Claude Code.

Generates the ``.claude/settings.json`` hook configuration and copies
hook scripts into the project's ``.claude/hooks/`` directory.

Usage::

    python -m harnesskit install                   # Install in current dir
    python -m harnesskit install --project-dir /x  # Install in specific project
    python -m harnesskit uninstall                  # Remove hooks
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

_HOOK_SCRIPTS = {
    "pre_tool_use.sh": "harnesskit-pre-tool-use.sh",
    "post_tool_use.sh": "harnesskit-post-tool-use.sh",
    "session_start.sh": "harnesskit-session-start.sh",
}

_HOOKS_SOURCE_DIR = Path(__file__).resolve().parent

# The settings.json fragment that registers HarnessKit hooks
HOOK_SETTINGS_FRAGMENT = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/harnesskit-pre-tool-use.sh",
                        "timeout": 10,
                        "statusMessage": "HarnessKit: checking permissions..."
                    }
                ]
            }
        ],
        "PostToolUse": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/harnesskit-post-tool-use.sh",
                        "timeout": 10,
                        "statusMessage": "HarnessKit: logging..."
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
                        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/harnesskit-session-start.sh",
                        "timeout": 10,
                        "statusMessage": "HarnessKit: loading config..."
                    }
                ]
            }
        ],
    }
}


def install_hooks(project_dir: str | Path = ".") -> list[str]:
    """Install HarnessKit hooks into a Claude Code project.

    1. Copies hook shell scripts to ``.claude/hooks/``
    2. Merges hook config into ``.claude/settings.json``

    Returns a list of actions taken.
    """
    root = Path(project_dir).resolve()
    hooks_dir = root / ".claude" / "hooks"
    settings_path = root / ".claude" / "settings.json"
    actions: list[str] = []

    # 1. Create hooks directory
    hooks_dir.mkdir(parents=True, exist_ok=True)
    actions.append(f"Created {hooks_dir}")

    # 2. Copy hook scripts
    for src_name, dst_name in _HOOK_SCRIPTS.items():
        src = _HOOKS_SOURCE_DIR / src_name
        dst = hooks_dir / dst_name
        if src.is_file():
            shutil.copy2(src, dst)
            # Make executable
            dst.chmod(dst.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            actions.append(f"Installed {dst_name}")
        else:
            # Write inline if source not found (e.g. installed via pip)
            _write_inline_hook(dst, src_name.replace(".sh", "").replace("_", "-"))
            actions.append(f"Generated {dst_name}")

    # 3. Merge settings.json
    existing: dict = {}
    if settings_path.is_file():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = {}

    merged = _merge_hook_settings(existing, HOOK_SETTINGS_FRAGMENT)
    settings_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    actions.append(f"Updated {settings_path}")

    return actions


def uninstall_hooks(project_dir: str | Path = ".") -> list[str]:
    """Remove HarnessKit hooks from a Claude Code project.

    Removes hook scripts and cleans the settings.json.
    """
    root = Path(project_dir).resolve()
    hooks_dir = root / ".claude" / "hooks"
    settings_path = root / ".claude" / "settings.json"
    actions: list[str] = []

    # 1. Remove hook scripts
    for dst_name in _HOOK_SCRIPTS.values():
        path = hooks_dir / dst_name
        if path.is_file():
            path.unlink()
            actions.append(f"Removed {dst_name}")

    # 2. Clean settings.json
    if settings_path.is_file():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}

        cleaned = _remove_harnesskit_hooks(data)
        settings_path.write_text(
            json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        actions.append(f"Cleaned {settings_path}")

    return actions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_hook_settings(existing: dict, fragment: dict) -> dict:
    """Merge HarnessKit hook entries into existing settings without
    overwriting non-HarnessKit hooks.
    """
    result = dict(existing)
    existing_hooks = result.get("hooks", {})

    for event_name, hook_entries in fragment.get("hooks", {}).items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = hook_entries
        else:
            # Remove any existing HarnessKit entries first
            cleaned = [
                entry for entry in existing_hooks[event_name]
                if not _is_harnesskit_entry(entry)
            ]
            cleaned.extend(hook_entries)
            existing_hooks[event_name] = cleaned

    result["hooks"] = existing_hooks
    return result


def _remove_harnesskit_hooks(data: dict) -> dict:
    """Remove all HarnessKit hook entries from settings."""
    result = dict(data)
    hooks = result.get("hooks", {})
    cleaned_hooks: dict = {}

    for event_name, entries in hooks.items():
        remaining = [e for e in entries if not _is_harnesskit_entry(e)]
        if remaining:
            cleaned_hooks[event_name] = remaining

    if cleaned_hooks:
        result["hooks"] = cleaned_hooks
    elif "hooks" in result:
        del result["hooks"]

    return result


def _is_harnesskit_entry(entry: dict) -> bool:
    """Check if a hook entry belongs to HarnessKit."""
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "harnesskit" in cmd.lower():
            return True
        status = hook.get("statusMessage", "")
        if "HarnessKit" in status:
            return True
    return False


def _write_inline_hook(path: Path, handler_name: str) -> None:
    """Write a self-contained hook script when source files aren't available."""
    script = f"""#!/usr/bin/env bash
# HarnessKit — {handler_name} hook for Claude Code
# Auto-generated by harnesskit install
set -euo pipefail
exec python3 -m harnesskit.hooks.enforcer {handler_name}
"""
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
