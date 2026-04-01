#!/usr/bin/env bash
# HarnessKit — PreToolUse hook for Claude Code
#
# This script is called by Claude Code before every tool execution.
# It delegates to the Python enforcer for policy evaluation.
#
# Install via: python -m harnesskit install
# stdin:  JSON event from Claude Code
# stdout: JSON decision (allow/deny/ask)
# exit 0: success (process JSON output)
# exit 2: blocking error (prevent action)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Delegate to Python enforcer
exec python3 -m harnesskit.hooks.enforcer pre-tool-use
