#!/usr/bin/env bash
# HarnessKit — SessionStart hook for Claude Code
#
# This script is called when a Claude Code session begins.
# It loads the HarnessKit config and injects project context.
#
# Install via: python -m harnesskit install

set -euo pipefail

exec python3 -m harnesskit.hooks.enforcer session-start
