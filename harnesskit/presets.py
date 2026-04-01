"""Ready-made harness configurations for common use cases.

Each preset function returns a fully configured ``HarnessConfig`` that users
can export immediately or customise further via the ``ConfigBuilder``.
"""

from __future__ import annotations

from .bootstrap import preset_standard as _bootstrap_standard, preset_minimal as _bootstrap_minimal, preset_full as _bootstrap_full
from .config import ConfigBuilder, HarnessConfig
from .permissions import (
    preset_permissive as _perm_permissive,
    preset_research as _perm_research,
    preset_restrictive as _perm_restrictive,
    preset_standard as _perm_standard,
)


def preset_dev_assistant() -> HarnessConfig:
    """A general-purpose development assistant.

    Can read/write files, run shell commands, use git, and plan tasks.
    """
    return (
        ConfigBuilder("dev-assistant")
        .description("General-purpose development assistant with balanced permissions")
        .add_tools([
            "BashTool", "FileReadTool", "FileEditTool", "FileWriteTool",
            "GlobTool", "GrepTool", "AgentTool", "TodoTool",
            "NotebookEditTool", "ToolSearch",
        ])
        .add_commands([
            "commit", "branch", "pr-create", "review-pr",
            "add-dir", "init", "clear", "compact", "resume",
            "doctor", "config",
        ])
        .set_permissions(_perm_standard())
        .set_bootstrap(_bootstrap_standard())
        .set_model("claude-sonnet-4-6", provider="anthropic")
        .build()
    )


def preset_code_reviewer() -> HarnessConfig:
    """Read-only code reviewer that can search and analyse but not modify."""
    return (
        ConfigBuilder("code-reviewer")
        .description("Read-only code reviewer for pull request analysis")
        .add_tools([
            "FileReadTool", "GlobTool", "GrepTool", "ToolSearch",
        ])
        .add_commands([
            "review-pr", "doctor", "compact",
        ])
        .set_permissions(_perm_restrictive())
        .set_bootstrap(_bootstrap_minimal())
        .set_model("claude-sonnet-4-6", provider="anthropic")
        .build()
    )


def preset_research_agent() -> HarnessConfig:
    """Research agent with web access but no file modification."""
    return (
        ConfigBuilder("research-agent")
        .description("Research agent with web access, read-only file system")
        .add_tools([
            "FileReadTool", "GlobTool", "GrepTool",
            "WebFetchTool", "WebSearchTool", "ToolSearch",
        ])
        .add_commands([
            "compact", "clear", "resume",
        ])
        .set_permissions(_perm_research())
        .set_bootstrap(_bootstrap_minimal())
        .set_model("claude-sonnet-4-6", provider="anthropic")
        .build()
    )


def preset_devops_agent() -> HarnessConfig:
    """DevOps/CI agent with shell access and git commands."""
    return (
        ConfigBuilder("devops-agent")
        .description("DevOps agent for CI/CD pipelines and infrastructure tasks")
        .add_tools([
            "BashTool", "FileReadTool", "FileEditTool", "FileWriteTool",
            "GlobTool", "GrepTool", "ToolSearch",
        ])
        .add_commands([
            "commit", "branch", "pr-create", "autofix-pr",
            "doctor", "bug-report", "config",
        ])
        .set_permissions(_perm_permissive())
        .set_bootstrap(_bootstrap_standard())
        .set_model("claude-sonnet-4-6", provider="anthropic")
        .build()
    )


def preset_safe_sandbox() -> HarnessConfig:
    """Maximally restricted sandbox for untrusted or experimental use."""
    return (
        ConfigBuilder("safe-sandbox")
        .description("Maximally restricted sandbox — read-only, no shell, no web")
        .add_tools([
            "FileReadTool", "GlobTool", "GrepTool",
        ])
        .add_commands([
            "clear", "compact",
        ])
        .set_permissions(_perm_restrictive())
        .set_bootstrap(_bootstrap_minimal())
        .build()
    )


PRESET_CONFIGS: dict[str, callable] = {
    "dev-assistant": preset_dev_assistant,
    "code-reviewer": preset_code_reviewer,
    "research-agent": preset_research_agent,
    "devops-agent": preset_devops_agent,
    "safe-sandbox": preset_safe_sandbox,
}
