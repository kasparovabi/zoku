"""Pattern detector — finds repeated tool sequences across sessions.

Scans all recorded session traces and discovers **subsequences** of tool
actions that appear multiple times.  These become candidate workflows
that the user can choose to automate.

Algorithm:
    1. Extract tool-name sequences from each session trace
    2. Find all contiguous subsequences of length >= MIN_LENGTH
    3. Count how many *distinct sessions* each subsequence appears in
    4. Keep subsequences that appear in >= MIN_OCCURRENCES sessions
    5. Remove subsequences that are subsets of longer discovered patterns
    6. Rank by frequency, then by length

Example::

    Session 1: Grep -> Read -> Edit -> Bash(test) -> Bash(commit)
    Session 2: Grep -> Read -> Edit -> Bash(test) -> Bash(commit)
    Session 3: Read -> Edit -> Bash(test) -> Bash(commit)

    Detected pattern: [Grep, Read, Edit, Bash, Bash] (2 sessions)
                      [Read, Edit, Bash, Bash]        (3 sessions)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .recorder import SessionTrace, Action, load_all_traces, _phantom_dir

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MIN_PATTERN_LENGTH = 3    # At least 3 steps to count as a pattern
MAX_PATTERN_LENGTH = 15   # Don't look for absurdly long patterns
MIN_OCCURRENCES = 2       # Must appear in at least 2 different sessions

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkflowPattern:
    """A discovered sequence of tool actions that repeats across sessions."""
    steps: tuple[str, ...]
    occurrence_count: int
    session_ids: tuple[str, ...]
    example_inputs: tuple[str, ...]  # sample input_summary from first occurrence

    @property
    def length(self) -> int:
        return len(self.steps)

    @property
    def name(self) -> str:
        """Auto-generate a readable name from the steps."""
        unique = []
        for s in self.steps:
            if s not in unique:
                unique.append(s)
        return " -> ".join(unique)

    def to_dict(self) -> dict:
        return {
            "steps": list(self.steps),
            "occurrence_count": self.occurrence_count,
            "session_ids": list(self.session_ids),
            "example_inputs": list(self.example_inputs),
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowPattern":
        return cls(
            steps=tuple(d.get("steps", [])),
            occurrence_count=d.get("occurrence_count", 0),
            session_ids=tuple(d.get("session_ids", [])),
            example_inputs=tuple(d.get("example_inputs", [])),
        )


# ---------------------------------------------------------------------------
# Subsequence extraction
# ---------------------------------------------------------------------------

def _extract_subsequences(
    sequence: tuple[str, ...],
    min_len: int = MIN_PATTERN_LENGTH,
    max_len: int = MAX_PATTERN_LENGTH,
) -> list[tuple[str, ...]]:
    """Return all contiguous subsequences of *sequence* within length bounds."""
    subs = []
    n = len(sequence)
    for length in range(min_len, min(max_len, n) + 1):
        for start in range(n - length + 1):
            subs.append(sequence[start:start + length])
    return subs


def _find_subsequence_in_actions(
    actions: list[Action],
    pattern: tuple[str, ...],
) -> list[Action] | None:
    """Return the first matching slice of Actions for *pattern*, or None."""
    tools = [a.tool for a in actions]
    plen = len(pattern)
    for i in range(len(tools) - plen + 1):
        if tuple(tools[i:i + plen]) == pattern:
            return actions[i:i + plen]
    return None


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------

def detect_patterns(
    traces: list[SessionTrace] | None = None,
    cwd: str | None = None,
    min_length: int = MIN_PATTERN_LENGTH,
    min_occurrences: int = MIN_OCCURRENCES,
) -> list[WorkflowPattern]:
    """Scan all session traces and return discovered workflow patterns.

    Patterns are returned sorted by (occurrence_count desc, length desc).
    """
    if traces is None:
        traces = load_all_traces(cwd)

    if len(traces) < min_occurrences:
        return []

    # 1. Build a map: subsequence -> set of session IDs
    subseq_sessions: dict[tuple[str, ...], set[str]] = {}
    subseq_examples: dict[tuple[str, ...], tuple[str, ...]] = {}

    for trace in traces:
        seq = trace.tool_sequence
        seen_in_this_trace: set[tuple[str, ...]] = set()

        for sub in _extract_subsequences(seq, min_len=min_length):
            if sub in seen_in_this_trace:
                continue
            seen_in_this_trace.add(sub)

            if sub not in subseq_sessions:
                subseq_sessions[sub] = set()
            subseq_sessions[sub].add(trace.session_id)

            # Store example inputs from the first occurrence
            if sub not in subseq_examples:
                match = _find_subsequence_in_actions(trace.actions, sub)
                if match:
                    subseq_examples[sub] = tuple(a.input_summary for a in match)

    # 2. Filter by minimum occurrences
    candidates = {
        sub: sessions
        for sub, sessions in subseq_sessions.items()
        if len(sessions) >= min_occurrences
    }

    if not candidates:
        return []

    # 3. Remove subsequences that are strict subsets of longer patterns
    sorted_by_length = sorted(candidates.keys(), key=len, reverse=True)
    kept: list[tuple[str, ...]] = []

    for sub in sorted_by_length:
        is_subset = False
        for longer in kept:
            if len(sub) < len(longer) and _is_contiguous_subset(sub, longer):
                # Only remove if the longer one has equal or higher count
                if len(candidates[longer]) >= len(candidates[sub]):
                    is_subset = True
                    break
        if not is_subset:
            kept.append(sub)

    # 4. Build WorkflowPattern objects
    patterns = []
    for sub in kept:
        sessions = candidates[sub]
        examples = subseq_examples.get(sub, ())
        patterns.append(WorkflowPattern(
            steps=sub,
            occurrence_count=len(sessions),
            session_ids=tuple(sorted(sessions)),
            example_inputs=examples,
        ))

    # 5. Sort by frequency then length
    patterns.sort(key=lambda p: (-p.occurrence_count, -p.length))
    return patterns


def _is_contiguous_subset(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """Check if *short* appears as a contiguous slice within *long*."""
    slen = len(short)
    for i in range(len(long) - slen + 1):
        if long[i:i + slen] == short:
            return True
    return False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _patterns_path(cwd: str | None = None) -> Path:
    return _phantom_dir(cwd) / "patterns.json"


def save_patterns(patterns: list[WorkflowPattern], cwd: str | None = None) -> Path:
    """Save discovered patterns to disk."""
    path = _patterns_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [p.to_dict() for p in patterns]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_patterns(cwd: str | None = None) -> list[WorkflowPattern]:
    """Load previously discovered patterns from disk."""
    path = _patterns_path(cwd)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [WorkflowPattern.from_dict(d) for d in data]
    except (json.JSONDecodeError, KeyError):
        return []
