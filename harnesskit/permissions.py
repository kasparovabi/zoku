"""Permission rule builder for agent harness configurations.

Defines what an agent is allowed — and explicitly forbidden — to do.
Provides both fine-grained rules and safety presets for common use cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Single permission rule
# ---------------------------------------------------------------------------

_SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9_*\-]+$")


@dataclass(frozen=True)
class PermissionRule:
    """One allow/deny directive.

    ``target`` is either an exact tool/command name or a prefix glob
    (e.g. ``"mcp*"``).  ``action`` decides whether the rule allows or
    blocks the target.
    """
    target: str
    action: Literal["allow", "deny"]
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.target or not _SAFE_PATTERN.match(self.target):
            raise ValueError(
                f"Invalid permission target: {self.target!r}. "
                "Targets may only contain alphanumerics, underscores, hyphens, and '*'."
            )

    @property
    def is_prefix(self) -> bool:
        return self.target.endswith("*")

    def matches(self, name: str) -> bool:
        lowered = name.lower()
        target = self.target.lower()
        if self.is_prefix:
            return lowered.startswith(target.rstrip("*"))
        return lowered == target


# ---------------------------------------------------------------------------
# Permission policy (ordered rule list)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PermissionPolicy:
    """Ordered collection of permission rules.

    Evaluation is first-match-wins: the first rule whose target matches the
    given tool/command name determines whether access is allowed or denied.
    If no rule matches, the *default_action* applies.
    """
    rules: tuple[PermissionRule, ...] = ()
    default_action: Literal["allow", "deny"] = "deny"

    def evaluate(self, name: str) -> tuple[Literal["allow", "deny"], str]:
        """Return ``(action, reason)`` for a tool/command *name*."""
        for rule in self.rules:
            if rule.matches(name):
                return rule.action, rule.reason
        reason = f"No explicit rule; default policy is {self.default_action}"
        return self.default_action, reason

    def is_allowed(self, name: str) -> bool:
        action, _ = self.evaluate(name)
        return action == "allow"

    def blocked_names(self, candidates: list[str]) -> list[str]:
        """Return names from *candidates* that this policy blocks."""
        return [n for n in candidates if not self.is_allowed(n)]

    def allowed_names(self, candidates: list[str]) -> list[str]:
        """Return names from *candidates* that this policy allows."""
        return [n for n in candidates if self.is_allowed(n)]

    def add_rule(self, rule: PermissionRule) -> "PermissionPolicy":
        """Return a new policy with *rule* appended."""
        return PermissionPolicy(
            rules=self.rules + (rule,),
            default_action=self.default_action,
        )

    def as_dict(self) -> dict:
        """Serialisable representation for config export."""
        return {
            "default_action": self.default_action,
            "rules": [
                {"target": r.target, "action": r.action, "reason": r.reason}
                for r in self.rules
            ],
        }


# ---------------------------------------------------------------------------
# Safety presets
# ---------------------------------------------------------------------------

def preset_restrictive() -> PermissionPolicy:
    """Very locked-down policy: only file-read and search tools allowed."""
    return PermissionPolicy(
        rules=(
            PermissionRule("FileReadTool", "allow", "Read-only file access"),
            PermissionRule("GlobTool", "allow", "File search"),
            PermissionRule("GrepTool", "allow", "Content search"),
            PermissionRule("ToolSearch", "allow", "Tool discovery"),
        ),
        default_action="deny",
    )


def preset_standard() -> PermissionPolicy:
    """Balanced policy for typical development workflows."""
    return PermissionPolicy(
        rules=(
            PermissionRule("FileReadTool", "allow", "Read file contents"),
            PermissionRule("FileEditTool", "allow", "Edit existing files"),
            PermissionRule("FileWriteTool", "allow", "Create new files"),
            PermissionRule("GlobTool", "allow", "File pattern search"),
            PermissionRule("GrepTool", "allow", "Content search"),
            PermissionRule("BashTool", "allow", "Shell command execution"),
            PermissionRule("AgentTool", "allow", "Sub-agent delegation"),
            PermissionRule("TodoTool", "allow", "Task planning"),
            PermissionRule("ToolSearch", "allow", "Tool discovery"),
            PermissionRule("NotebookEditTool", "allow", "Jupyter notebook editing"),
            PermissionRule("mcp*", "deny", "MCP tools require explicit opt-in"),
        ),
        default_action="deny",
    )


def preset_permissive() -> PermissionPolicy:
    """Allow everything except known dangerous patterns."""
    return PermissionPolicy(
        rules=(
            PermissionRule("mcp*", "deny", "MCP tools require explicit opt-in"),
        ),
        default_action="allow",
    )


def preset_research() -> PermissionPolicy:
    """Read-only with web access, suitable for research tasks."""
    return PermissionPolicy(
        rules=(
            PermissionRule("FileReadTool", "allow", "Read file contents"),
            PermissionRule("GlobTool", "allow", "File pattern search"),
            PermissionRule("GrepTool", "allow", "Content search"),
            PermissionRule("WebFetchTool", "allow", "Fetch web pages"),
            PermissionRule("WebSearchTool", "allow", "Web search"),
            PermissionRule("ToolSearch", "allow", "Tool discovery"),
            PermissionRule("BashTool", "deny", "No shell access in research mode"),
            PermissionRule("FileEditTool", "deny", "No file modification in research mode"),
            PermissionRule("FileWriteTool", "deny", "No file creation in research mode"),
        ),
        default_action="deny",
    )


PRESETS: dict[str, callable] = {
    "restrictive": preset_restrictive,
    "standard": preset_standard,
    "permissive": preset_permissive,
    "research": preset_research,
}
