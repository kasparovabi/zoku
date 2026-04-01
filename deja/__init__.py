"""Deja — invisible automation layer for Claude Code.

Watches every tool action, detects repeated patterns across sessions,
and suggests automating them as replayable workflows.

Runs as native Claude Code hooks (PostToolUse, Stop, SessionStart).
"""

from __future__ import annotations

__version__ = "0.1.0"
