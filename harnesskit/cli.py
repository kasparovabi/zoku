"""HarnessKit CLI — interactive wizard and command interface.

Usage::

    python -m harnesskit init                              # Interactive wizard
    python -m harnesskit preset <name>                     # Export a preset config
    python -m harnesskit catalog                           # Browse tool/command catalog
    python -m harnesskit audit <file>                      # Audit an existing config
    python -m harnesskit presets                            # List available presets
    python -m harnesskit adapt <file> --target claude-code # Adapt for a CLI tool
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalog import load_catalog
from .config import ConfigBuilder, HarnessConfig
from .permissions import PRESETS as PERMISSION_PRESETS
from .bootstrap import PIPELINE_PRESETS, STAGE_LIBRARY
from .presets import PRESET_CONFIGS
from .security import audit_config, sanitise_name
from .adapters import adapt, adapt_all, SUPPORTED_TARGETS


def _print(msg: str = "") -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    """Interactive wizard to create a new harness config."""
    _print("=== HarnessKit Configuration Wizard ===")
    _print()

    # 1. Project name
    project_name = _ask("Project name", default="my-agent")
    try:
        project_name = sanitise_name(project_name)
    except ValueError as exc:
        _print(f"Error: {exc}")
        return 1

    builder = ConfigBuilder(project_name)

    # 2. Description
    desc = _ask("Short description (optional)", default="")
    if desc:
        builder.description(desc)

    # 3. Permission preset
    _print()
    _print("Available permission presets:")
    for name in sorted(PERMISSION_PRESETS):
        _print(f"  - {name}")
    perm_preset = _ask("Permission preset", default="standard")
    if perm_preset not in PERMISSION_PRESETS:
        _print(f"Unknown preset '{perm_preset}', using 'standard'.")
        perm_preset = "standard"
    builder.set_permission_preset(perm_preset)

    # 4. Bootstrap preset
    _print()
    _print("Available bootstrap presets:")
    for name in sorted(PIPELINE_PRESETS):
        _print(f"  - {name}")
    boot_preset = _ask("Bootstrap preset", default="standard")
    if boot_preset not in PIPELINE_PRESETS:
        _print(f"Unknown preset '{boot_preset}', using 'standard'.")
        boot_preset = "standard"
    builder.set_bootstrap_preset(boot_preset)

    # 5. Tool selection
    catalog = load_catalog()
    _print()
    _print(f"Available tool categories: {', '.join(catalog.categories)}")
    tool_input = _ask(
        "Add tools by category (comma-separated) or 'skip'",
        default="skip",
    )
    if tool_input.lower() != "skip":
        for cat in (c.strip() for c in tool_input.split(",")):
            if cat:
                builder.add_tools_by_category(cat, catalog)

    # 6. Model
    _print()
    model_name = _ask("Model name (optional)", default="")
    if model_name:
        provider = _ask("Provider", default="anthropic")
        builder.set_model(model_name, provider=provider)

    # 7. Build and audit
    config = builder.build()
    report = config.audit()

    _print()
    _print(config.summary())
    _print()
    _print(report.as_markdown())

    # 8. Export
    _print()
    output = args.output or f"{project_name}.harnesskit.json"
    config.export_json(output)
    _print(f"Configuration written to: {output}")
    return 0


def cmd_preset(args: argparse.Namespace) -> int:
    """Export a preset configuration."""
    name = args.name
    if name not in PRESET_CONFIGS:
        _print(f"Unknown preset '{name}'.")
        _print(f"Available: {', '.join(sorted(PRESET_CONFIGS))}")
        return 1
    config = PRESET_CONFIGS[name]()
    output = args.output or f"{name}.harnesskit.json"
    config.export_json(output)
    _print(config.summary())
    _print()
    _print(f"Configuration written to: {output}")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    """Browse the tool/command catalog."""
    catalog = load_catalog()
    kind = args.kind
    query = args.query
    limit = args.limit

    if query:
        entries = catalog.search(query, limit=limit)
        _print(f"Search results for '{query}' ({len(entries)} matches):")
    elif kind == "tools":
        entries = catalog.tools[:limit]
        _print(f"Tools ({len(catalog.tools)} total, showing {len(entries)}):")
    elif kind == "commands":
        entries = catalog.commands[:limit]
        _print(f"Commands ({len(catalog.commands)} total, showing {len(entries)}):")
    elif kind == "categories":
        _print(f"Categories ({len(catalog.categories)}):")
        for cat in catalog.categories:
            count = len(catalog.by_category(cat))
            _print(f"  {cat} ({count} entries)")
        return 0
    else:
        entries = catalog.entries[:limit]
        _print(f"All entries ({len(catalog.entries)} total, showing {len(entries)}):")

    _print()
    for e in entries:
        _print(f"  [{e.kind:7s}] [{e.category:10s}] {e.name}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit an existing configuration file."""
    path = Path(args.file)
    if not path.is_file():
        _print(f"File not found: {path}")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _print(f"Failed to parse {path}: {exc}")
        return 1
    if not isinstance(data, dict):
        _print("Configuration must be a JSON object.")
        return 1
    report = audit_config(data)
    _print(report.as_markdown())
    return 0 if report.passed else 1


def cmd_presets_list(args: argparse.Namespace) -> int:
    """List available presets."""
    _print("Available configuration presets:")
    _print()
    for name in sorted(PRESET_CONFIGS):
        config = PRESET_CONFIGS[name]()
        desc = config.description or "(no description)"
        score = config.audit().score
        _print(f"  {name:20s}  {desc:50s}  [safety: {score}/100]")
    return 0


def cmd_stages(args: argparse.Namespace) -> int:
    """List available bootstrap stages."""
    _print("Available bootstrap stages:")
    _print()
    for name, stage in sorted(STAGE_LIBRARY.items(), key=lambda kv: kv[1].order):
        _print(f"  {stage.order:3d}  [{stage.kind:8s}]  {name}: {stage.description}")
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    """Adapt a HarnessKit config for a specific CLI tool."""
    path = Path(args.file)
    if not path.is_file():
        _print(f"File not found: {path}")
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _print(f"Failed to parse {path}: {exc}")
        return 1

    # Reconstruct HarnessConfig from JSON
    from .config import HarnessConfig, ModelConfig
    from .permissions import PermissionPolicy, PermissionRule
    from .bootstrap import BootstrapPipeline, Stage

    # Rebuild permissions
    perm_data = data.get("permissions", {})
    rules = []
    for r in perm_data.get("rules", []):
        rules.append(PermissionRule(
            target=r["target"],
            action=r["action"],
            reason=r.get("reason", ""),
        ))
    permissions = PermissionPolicy(
        rules=tuple(rules),
        default_action=perm_data.get("default_action", "deny"),
    )

    # Rebuild bootstrap
    boot_data = data.get("bootstrap", {})
    stages = []
    for s in boot_data.get("stages", []):
        stages.append(Stage(
            name=s["name"],
            kind=s["kind"],
            description=s.get("description", ""),
            order=s.get("order", 0),
        ))
    bootstrap = BootstrapPipeline(stages=tuple(stages))

    # Rebuild model
    model_data = data.get("model", {})
    model = ModelConfig(
        name=model_data.get("name", ""),
        provider=model_data.get("provider", ""),
        max_tokens=model_data.get("max_tokens", 4096),
        temperature=model_data.get("temperature", 0.0),
    )

    config = HarnessConfig(
        project_name=data.get("project_name", "unknown"),
        description=data.get("description", ""),
        tools=tuple(data.get("tools", [])),
        commands=tuple(data.get("commands", [])),
        permissions=permissions,
        bootstrap=bootstrap,
        model=model,
    )

    output_dir = Path(args.output_dir)
    targets = list(SUPPORTED_TARGETS) if args.target == "all" else [args.target]

    for target in targets:
        try:
            result = adapt(config, target)
        except ValueError as exc:
            _print(f"Error: {exc}")
            return 1

        _print(f"=== {target} ===")
        _print(result.preview())
        written = result.write(output_dir)
        for p in written:
            _print(f"  Written: {p}")
        _print()

    return 0


def cmd_install(args: argparse.Namespace) -> int:
    """Install HarnessKit hooks into Claude Code."""
    from .hooks.installer import install_hooks
    project_dir = args.project_dir or "."
    _print("Installing HarnessKit hooks into Claude Code...")
    _print()
    actions = install_hooks(project_dir)
    for action in actions:
        _print(f"  {action}")
    _print()
    _print("HarnessKit is now active as a Claude Code hook.")
    _print("It will enforce your .harnesskit.json policy on every tool call.")
    _print()
    _print("Next steps:")
    _print("  1. Create a config: python -m harnesskit preset dev-assistant")
    _print("  2. Start Claude Code — HarnessKit hooks will load automatically")
    _print("  3. Check /hooks in Claude Code to verify")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove HarnessKit hooks from Claude Code."""
    from .hooks.installer import uninstall_hooks
    project_dir = args.project_dir or "."
    _print("Removing HarnessKit hooks from Claude Code...")
    _print()
    actions = uninstall_hooks(project_dir)
    if actions:
        for action in actions:
            _print(f"  {action}")
    else:
        _print("  No HarnessKit hooks found.")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        _print()
        return default
    return answer or default


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harnesskit",
        description="HarnessKit — No-code agent harness configuration toolkit",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="Interactive configuration wizard")
    p_init.add_argument("-o", "--output", help="Output file path")

    # preset
    p_preset = sub.add_parser("preset", help="Export a preset configuration")
    p_preset.add_argument("name", help="Preset name")
    p_preset.add_argument("-o", "--output", help="Output file path")

    # catalog
    p_cat = sub.add_parser("catalog", help="Browse tool/command catalog")
    p_cat.add_argument("kind", nargs="?", choices=["tools", "commands", "categories"],
                        help="Filter by kind")
    p_cat.add_argument("-q", "--query", help="Search query")
    p_cat.add_argument("-l", "--limit", type=int, default=30, help="Max results")

    # audit
    p_audit = sub.add_parser("audit", help="Audit a configuration file")
    p_audit.add_argument("file", help="Path to .harnesskit.json file")

    # presets
    sub.add_parser("presets", help="List available preset configurations")

    # stages
    sub.add_parser("stages", help="List available bootstrap stages")

    # adapt
    p_adapt = sub.add_parser("adapt", help="Adapt config for a specific CLI tool")
    p_adapt.add_argument("file", help="Path to .harnesskit.json file")
    p_adapt.add_argument("-t", "--target", required=True,
                         choices=list(SUPPORTED_TARGETS) + ["all"],
                         help="Target CLI tool")
    p_adapt.add_argument("-d", "--output-dir", default=".",
                         help="Output directory (default: current dir)")

    # install
    p_install = sub.add_parser("install", help="Install HarnessKit hooks into Claude Code")
    p_install.add_argument("-p", "--project-dir", help="Project directory (default: cwd)")

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Remove HarnessKit hooks from Claude Code")
    p_uninstall.add_argument("-p", "--project-dir", help="Project directory (default: cwd)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "init": cmd_init,
        "preset": cmd_preset,
        "catalog": cmd_catalog,
        "audit": cmd_audit,
        "presets": cmd_presets_list,
        "stages": cmd_stages,
        "adapt": cmd_adapt,
        "install": cmd_install,
        "uninstall": cmd_uninstall,
    }

    if args.command in handlers:
        return handlers[args.command](args)

    parser.print_help()
    return 0
