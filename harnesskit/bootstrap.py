"""Bootstrap pipeline builder.

Defines the startup sequence an agent follows when a new session begins.
Users can pick from predefined stage templates or compose custom pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Stage definition
# ---------------------------------------------------------------------------

StageKind = Literal["prefetch", "guard", "load", "init", "route", "loop"]

_VALID_KINDS: frozenset[str] = frozenset(StageKind.__args__)  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Stage:
    """A single bootstrap stage."""
    name: str
    kind: StageKind
    description: str
    order: int

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Stage name must not be empty.")
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"Invalid stage kind {self.kind!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_KINDS))}"
            )
        if self.order < 0:
            raise ValueError(f"Stage order must be non-negative, got {self.order}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BootstrapPipeline:
    """Ordered sequence of bootstrap stages."""
    stages: tuple[Stage, ...]

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.stages)

    def add_stage(self, stage: Stage) -> "BootstrapPipeline":
        """Return a new pipeline with *stage* inserted at the correct order position."""
        stages = list(self.stages)
        stages.append(stage)
        stages.sort(key=lambda s: s.order)
        return BootstrapPipeline(stages=tuple(stages))

    def remove_stage(self, name: str) -> "BootstrapPipeline":
        """Return a new pipeline without the stage named *name*."""
        return BootstrapPipeline(
            stages=tuple(s for s in self.stages if s.name != name)
        )

    def as_dict(self) -> list[dict]:
        """Serialisable representation for config export."""
        return [
            {
                "name": s.name,
                "kind": s.kind,
                "description": s.description,
                "order": s.order,
            }
            for s in self.stages
        ]


# ---------------------------------------------------------------------------
# Predefined stage library
# ---------------------------------------------------------------------------

STAGE_LIBRARY: dict[str, Stage] = {
    "prefetch": Stage(
        name="prefetch",
        kind="prefetch",
        description="Pre-load project metadata, keychains, and environment info",
        order=10,
    ),
    "environment_guard": Stage(
        name="environment_guard",
        kind="guard",
        description="Validate environment variables, runtime version, and platform compatibility",
        order=20,
    ),
    "trust_gate": Stage(
        name="trust_gate",
        kind="guard",
        description="Verify workspace trust level before granting elevated permissions",
        order=30,
    ),
    "load_tools": Stage(
        name="load_tools",
        kind="load",
        description="Assemble the tool pool based on permission policy",
        order=40,
    ),
    "load_commands": Stage(
        name="load_commands",
        kind="load",
        description="Load available commands and slash-command registry",
        order=41,
    ),
    "load_plugins": Stage(
        name="load_plugins",
        kind="load",
        description="Discover and load plugin extensions",
        order=42,
    ),
    "deferred_init": Stage(
        name="deferred_init",
        kind="init",
        description="Run deferred initialisation (skills, MCP servers, hooks) after trust is confirmed",
        order=50,
    ),
    "session_hooks": Stage(
        name="session_hooks",
        kind="init",
        description="Execute session-start hooks for custom setup logic",
        order=55,
    ),
    "mode_router": Stage(
        name="mode_router",
        kind="route",
        description="Route to correct execution mode (local / remote / SSH / teleport)",
        order=60,
    ),
    "query_loop": Stage(
        name="query_loop",
        kind="loop",
        description="Enter the main prompt-response loop with the LLM",
        order=100,
    ),
}

# ---------------------------------------------------------------------------
# Pipeline presets
# ---------------------------------------------------------------------------

def preset_minimal() -> BootstrapPipeline:
    """Bare-minimum pipeline: load tools, enter query loop."""
    return BootstrapPipeline(stages=(
        STAGE_LIBRARY["load_tools"],
        STAGE_LIBRARY["query_loop"],
    ))


def preset_standard() -> BootstrapPipeline:
    """Balanced startup matching typical Claude Code behaviour."""
    return BootstrapPipeline(stages=(
        STAGE_LIBRARY["prefetch"],
        STAGE_LIBRARY["environment_guard"],
        STAGE_LIBRARY["trust_gate"],
        STAGE_LIBRARY["load_tools"],
        STAGE_LIBRARY["load_commands"],
        STAGE_LIBRARY["deferred_init"],
        STAGE_LIBRARY["mode_router"],
        STAGE_LIBRARY["query_loop"],
    ))


def preset_full() -> BootstrapPipeline:
    """Full pipeline with all available stages."""
    ordered = sorted(STAGE_LIBRARY.values(), key=lambda s: s.order)
    return BootstrapPipeline(stages=tuple(ordered))


PIPELINE_PRESETS: dict[str, callable] = {
    "minimal": preset_minimal,
    "standard": preset_standard,
    "full": preset_full,
}
