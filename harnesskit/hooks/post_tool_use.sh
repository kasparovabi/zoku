#!/usr/bin/env bash
# HarnessKit — PostToolUse hook for Claude Code
#
# This script is called by Claude Code after every tool execution.
# It logs the event and optionally flags secret leaks in tool results.
#
# Install via: python -m harnesskit install
# stdin:  JSON event from Claude Code
# stdout: JSON decision (allow/block)

set -euo pipefail

exec python3 -m harnesskit.hooks.enforcer post-tool-use
