"""Unified tool and command catalog with categories, search, and filtering.

Loads the reference data snapshots and provides a structured, queryable
catalog that HarnessKit consumers use to select which capabilities their
agent harness should expose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REF_DIR = Path(__file__).resolve().parent / "data"
_TOOLS_SNAPSHOT = _REF_DIR / "tools_snapshot.json"
_COMMANDS_SNAPSHOT = _REF_DIR / "commands_snapshot.json"

# ---------------------------------------------------------------------------
# Category taxonomy — hand-curated from source_hint directory structure
# ---------------------------------------------------------------------------

_TOOL_CATEGORY_RULES: list[tuple[str, str]] = [
    ("AgentTool/built-in", "agent"),
    ("AgentTool", "agent"),
    ("BashTool", "shell"),
    ("FileReadTool", "file-read"),
    ("FileEditTool", "file-edit"),
    ("FileWriteTool", "file-write"),
    ("GlobTool", "search"),
    ("GrepTool", "search"),
    ("NotebookEditTool", "notebook"),
    ("MemoryTool", "memory"),
    ("WebFetchTool", "web"),
    ("WebSearchTool", "web"),
    ("mcp", "mcp"),
    ("TodoTool", "planning"),
    ("ToolSearch", "search"),
]

_COMMAND_CATEGORY_RULES: list[tuple[str, str]] = [
    ("commit", "git"),
    ("branch", "git"),
    ("pr-", "git"),
    ("autofix-pr", "git"),
    ("review-pr", "git"),
    ("add-dir", "workspace"),
    ("init", "workspace"),
    ("config", "config"),
    ("clear", "session"),
    ("compact", "session"),
    ("resume", "session"),
    ("login", "auth"),
    ("logout", "auth"),
    ("doctor", "diagnostics"),
    ("bug-report", "diagnostics"),
    ("agents", "agent"),
    ("advisor", "agent"),
    ("mcp", "mcp"),
    ("skill", "skill"),
    ("hook", "hook"),
    ("vim", "editor"),
]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CatalogEntry:
    """A single tool or command in the catalog."""
    name: str
    kind: Literal["tool", "command"]
    source_hint: str
    responsibility: str
    category: str

    def matches(self, query: str) -> bool:
        """Case-insensitive substring match against name, category, or responsibility."""
        q = query.lower()
        return (
            q in self.name.lower()
            or q in self.category.lower()
            or q in self.responsibility.lower()
        )


@dataclass(frozen=True)
class Catalog:
    """Immutable, queryable collection of tools and commands."""
    entries: tuple[CatalogEntry, ...]

    # -- Queries -----------------------------------------------------------

    @property
    def tools(self) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "tool")

    @property
    def commands(self) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.kind == "command")

    @property
    def categories(self) -> tuple[str, ...]:
        """Sorted unique categories."""
        return tuple(sorted({e.category for e in self.entries}))

    def by_category(self, category: str) -> tuple[CatalogEntry, ...]:
        cat = category.lower()
        return tuple(e for e in self.entries if e.category == cat)

    def search(self, query: str, limit: int = 25) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.matches(query))[:limit]

    def select(self, names: list[str]) -> tuple[CatalogEntry, ...]:
        """Select entries by exact name list (case-insensitive)."""
        lowered = {n.lower() for n in names}
        return tuple(e for e in self.entries if e.name.lower() in lowered)

    def unique_names(self, kind: Literal["tool", "command"] | None = None) -> tuple[str, ...]:
        """Deduplicated, sorted entry names optionally filtered by kind."""
        entries = self.entries
        if kind is not None:
            entries = tuple(e for e in entries if e.kind == kind)
        return tuple(sorted({e.name for e in entries}))


# ---------------------------------------------------------------------------
# Category inference
# ---------------------------------------------------------------------------

def _infer_category(name: str, source_hint: str, rules: list[tuple[str, str]]) -> str:
    """Return the first matching category from *rules*, or 'general'."""
    combined = f"{name} {source_hint}".lower()
    for pattern, category in rules:
        if pattern.lower() in combined:
            return category
    return "general"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        return []
    return data


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    """Build the full catalog from reference-data snapshots.

    Each raw JSON entry must have ``name``, ``source_hint``, and
    ``responsibility`` keys.  Entries missing any of these are silently
    skipped so a malformed snapshot never crashes the loader.
    """
    entries: list[CatalogEntry] = []

    for raw in _load_json(_TOOLS_SNAPSHOT):
        name = raw.get("name", "")
        hint = raw.get("source_hint", "")
        resp = raw.get("responsibility", "")
        if not name:
            continue
        entries.append(CatalogEntry(
            name=name,
            kind="tool",
            source_hint=hint,
            responsibility=resp,
            category=_infer_category(name, hint, _TOOL_CATEGORY_RULES),
        ))

    for raw in _load_json(_COMMANDS_SNAPSHOT):
        name = raw.get("name", "")
        hint = raw.get("source_hint", "")
        resp = raw.get("responsibility", "")
        if not name:
            continue
        entries.append(CatalogEntry(
            name=name,
            kind="command",
            source_hint=hint,
            responsibility=resp,
            category=_infer_category(name, hint, _COMMAND_CATEGORY_RULES),
        ))

    return Catalog(entries=tuple(entries))
