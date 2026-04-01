"""Configuration engine — build, validate, and export agent harness configs.

A ``HarnessConfig`` is the central artefact that HarnessKit produces.
It bundles tool/command selections, permission policy, bootstrap pipeline,
model preferences, and metadata into a single validated, exportable object.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from . import __version__
from .bootstrap import BootstrapPipeline, PIPELINE_PRESETS, preset_standard as _default_pipeline
from .catalog import Catalog, CatalogEntry, load_catalog
from .permissions import PermissionPolicy, PRESETS as _PERMISSION_PRESETS, preset_standard as _default_perms
from .security import AuditReport, audit_config, sanitise_name

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelConfig:
    """Which LLM to target and with what parameters."""
    name: str = ""
    provider: str = ""
    max_tokens: int = 4096
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be at least 1")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")

    def as_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.name:
            d["name"] = self.name
        if self.provider:
            d["provider"] = self.provider
        d["max_tokens"] = self.max_tokens
        d["temperature"] = self.temperature
        return d


# ---------------------------------------------------------------------------
# Harness configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HarnessConfig:
    """Complete agent harness configuration."""
    project_name: str
    description: str = ""
    tools: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    permissions: PermissionPolicy = field(default_factory=_default_perms)
    bootstrap: BootstrapPipeline = field(default_factory=_default_pipeline)
    model: ModelConfig = field(default_factory=ModelConfig)

    def __post_init__(self) -> None:
        sanitise_name(self.project_name)

    # -- Serialisation -----------------------------------------------------

    def as_dict(self) -> dict:
        """Full dictionary representation ready for JSON/YAML export."""
        return {
            "harnesskit_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_name": self.project_name,
            "description": self.description,
            "tools": list(self.tools),
            "commands": list(self.commands),
            "permissions": self.permissions.as_dict(),
            "bootstrap": {"stages": self.bootstrap.as_dict()},
            "model": self.model.as_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent, ensure_ascii=False)

    def export_json(self, path: str | Path) -> Path:
        """Write config to a JSON file and return the path."""
        p = Path(path)
        p.write_text(self.to_json(), encoding="utf-8")
        return p

    # -- Audit -------------------------------------------------------------

    def audit(self) -> AuditReport:
        """Run a security audit on this configuration."""
        return audit_config(self.as_dict())

    # -- Summary -----------------------------------------------------------

    def summary(self) -> str:
        """Human-readable one-page summary."""
        lines = [
            f"# HarnessKit Configuration: {self.project_name}",
            "",
        ]
        if self.description:
            lines.append(f"{self.description}")
            lines.append("")
        lines.append(f"**Tools:** {len(self.tools)} selected")
        lines.append(f"**Commands:** {len(self.commands)} selected")
        lines.append(f"**Permission default:** {self.permissions.default_action}")
        lines.append(f"**Permission rules:** {len(self.permissions.rules)}")
        lines.append(f"**Bootstrap stages:** {len(self.bootstrap.stages)}")
        if self.model.name:
            lines.append(f"**Model:** {self.model.name} ({self.model.provider})")

        report = self.audit()
        lines.append("")
        lines.append(f"**Safety score:** {report.score}/100")
        if not report.passed:
            lines.append("**WARNING:** Critical security findings detected. Run `audit` for details.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder (mutable helper that produces an immutable HarnessConfig)
# ---------------------------------------------------------------------------

class ConfigBuilder:
    """Fluent builder for constructing a ``HarnessConfig`` step by step.

    This is what the CLI wizard and programmatic users interact with.
    Call ``.build()`` to get a validated, immutable ``HarnessConfig``.
    """

    def __init__(self, project_name: str) -> None:
        self._project_name = sanitise_name(project_name)
        self._description: str = ""
        self._tools: list[str] = []
        self._commands: list[str] = []
        self._permissions: PermissionPolicy = _default_perms()
        self._bootstrap: BootstrapPipeline = _default_pipeline()
        self._model: ModelConfig = ModelConfig()

    # -- Setters -----------------------------------------------------------

    def description(self, desc: str) -> "ConfigBuilder":
        self._description = desc.strip()
        return self

    def add_tools(self, names: list[str]) -> "ConfigBuilder":
        for n in names:
            sanitise_name(n)
        self._tools.extend(names)
        return self

    def add_tools_by_category(self, category: str, catalog: Catalog | None = None) -> "ConfigBuilder":
        cat = catalog or load_catalog()
        entries = cat.by_category(category)
        self._tools.extend(e.name for e in entries if e.kind == "tool")
        return self

    def add_commands(self, names: list[str]) -> "ConfigBuilder":
        for n in names:
            sanitise_name(n)
        self._commands.extend(names)
        return self

    def set_permission_preset(self, preset_name: str) -> "ConfigBuilder":
        if preset_name not in _PERMISSION_PRESETS:
            raise ValueError(
                f"Unknown permission preset {preset_name!r}. "
                f"Available: {', '.join(sorted(_PERMISSION_PRESETS))}"
            )
        self._permissions = _PERMISSION_PRESETS[preset_name]()
        return self

    def set_permissions(self, policy: PermissionPolicy) -> "ConfigBuilder":
        self._permissions = policy
        return self

    def set_bootstrap_preset(self, preset_name: str) -> "ConfigBuilder":
        if preset_name not in PIPELINE_PRESETS:
            raise ValueError(
                f"Unknown bootstrap preset {preset_name!r}. "
                f"Available: {', '.join(sorted(PIPELINE_PRESETS))}"
            )
        self._bootstrap = PIPELINE_PRESETS[preset_name]()
        return self

    def set_bootstrap(self, pipeline: BootstrapPipeline) -> "ConfigBuilder":
        self._bootstrap = pipeline
        return self

    def set_model(self, name: str, provider: str = "", max_tokens: int = 4096, temperature: float = 0.0) -> "ConfigBuilder":
        self._model = ModelConfig(
            name=name,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return self

    # -- Build -------------------------------------------------------------

    def build(self) -> HarnessConfig:
        """Produce a validated, immutable ``HarnessConfig``."""
        # Deduplicate while preserving order
        seen_tools: set[str] = set()
        unique_tools: list[str] = []
        for t in self._tools:
            if t not in seen_tools:
                seen_tools.add(t)
                unique_tools.append(t)

        seen_cmds: set[str] = set()
        unique_cmds: list[str] = []
        for c in self._commands:
            if c not in seen_cmds:
                seen_cmds.add(c)
                unique_cmds.append(c)

        return HarnessConfig(
            project_name=self._project_name,
            description=self._description,
            tools=tuple(unique_tools),
            commands=tuple(unique_cmds),
            permissions=self._permissions,
            bootstrap=self._bootstrap,
            model=self._model,
        )
