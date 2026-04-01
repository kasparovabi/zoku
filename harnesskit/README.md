# HarnessKit

**No-code agent harness configuration toolkit.**

Build, validate, audit, and export AI agent harness configurations — without writing code.

HarnessKit provides a structured way to define what an AI agent can do, what it cannot do, and how it starts up. It draws on real-world agent architecture patterns (tool catalogues, permission policies, bootstrap pipelines) and packages them into a single, auditable configuration file.

---

## Why HarnessKit?

Every AI agent system needs to answer the same questions:

- **Which tools** can the agent use? (file access, shell, web, search, etc.)
- **What permissions** does it have? (can it delete files? run arbitrary commands?)
- **How does it start?** (environment checks, trust gates, plugin loading)
- **Is the configuration safe?** (no leaked secrets, no overly permissive rules)

HarnessKit turns these questions into a repeatable, auditable process.

---

## Installation

No external dependencies required. HarnessKit uses only the Python standard library.

```bash
git clone https://github.com/kasparovabi/claw-code.git
cd claw-code
```

---

## Quick Start

### 1. List available presets

```bash
python -m harnesskit presets
```

```
Available configuration presets:

  code-reviewer         Read-only code reviewer for pull request analysis   [safety: 88/100]
  dev-assistant         General-purpose development assistant               [safety: 90/100]
  devops-agent          DevOps agent for CI/CD pipelines                    [safety: 90/100]
  research-agent        Research agent with web access, read-only FS        [safety: 88/100]
  safe-sandbox          Maximally restricted sandbox                        [safety: 86/100]
```

### 2. Export a preset

```bash
python -m harnesskit preset dev-assistant
```

This creates `dev-assistant.harnesskit.json` — a complete, audited configuration.

### 3. Interactive wizard

```bash
python -m harnesskit init
```

Walk through project name, permission level, bootstrap pipeline, tool selection, and model choice step by step.

### 4. Audit an existing config

```bash
python -m harnesskit audit my-config.harnesskit.json
```

Checks for leaked secrets, overly permissive rules, missing security stages, and more.

### 5. Browse the catalog

```bash
python -m harnesskit catalog categories     # See all tool/command categories
python -m harnesskit catalog tools -l 20    # List tools
python -m harnesskit catalog -q "bash"      # Search
python -m harnesskit stages                 # List bootstrap stages
```

---

## Architecture

```
harnesskit/
  __init__.py        # Package metadata
  __main__.py        # python -m harnesskit entrypoint
  catalog.py         # Tool & command catalog with categories and search
  permissions.py     # Permission rules, policies, and safety presets
  bootstrap.py       # Bootstrap pipeline stages and presets
  config.py          # Configuration engine, builder, and JSON export
  security.py        # Secret detection, input sanitisation, safety audit
  presets.py         # Ready-made configurations for common use cases
  cli.py             # CLI wizard and command interface
```

### Key concepts

| Concept | What it does |
|---|---|
| **Catalog** | Queryable index of 180+ tools and 200+ commands with categories |
| **PermissionPolicy** | Ordered allow/deny rules that control what an agent can access |
| **BootstrapPipeline** | Ordered startup stages (prefetch, guards, loading, routing, loop) |
| **HarnessConfig** | The final artefact: bundles tools, commands, permissions, bootstrap, model |
| **AuditReport** | Security scan with a 0-100 safety score |
| **ConfigBuilder** | Fluent API for building configs step by step |

---

## Security Features

HarnessKit takes security seriously:

- **Input sanitisation** — All names validated against strict patterns; shell meta-characters rejected
- **Secret scanning** — Configs are scanned for AWS keys, GitHub tokens, API keys, private keys, and more
- **Safety scoring** — Every config gets a 0-100 safety score based on permission strictness, bootstrap hardening, and secret presence
- **Audit reports** — Markdown-formatted reports with severity levels (INFO / WARN / CRIT)
- **Immutable data** — Core data structures use frozen dataclasses to prevent accidental mutation
- **First-match-wins policy** — Permission evaluation follows a predictable, auditable order

---

## Programmatic Usage

```python
from harnesskit.config import ConfigBuilder

config = (
    ConfigBuilder("my-agent")
    .description("Custom research assistant")
    .add_tools(["FileReadTool", "GrepTool", "WebSearchTool"])
    .add_commands(["compact", "clear"])
    .set_permission_preset("research")
    .set_bootstrap_preset("minimal")
    .set_model("claude-sonnet-4-6", provider="anthropic")
    .build()
)

# Export
config.export_json("my-agent.harnesskit.json")

# Audit
report = config.audit()
print(f"Safety score: {report.score}/100")
print(report.as_markdown())
```

---

## Permission Presets

| Preset | Default | Shell | File Write | Web | MCP |
|---|---|---|---|---|---|
| `restrictive` | deny | no | no | no | no |
| `standard` | deny | yes | yes | no | no |
| `permissive` | allow | yes | yes | yes | no |
| `research` | deny | no | no | yes | no |

---

## Bootstrap Presets

| Preset | Stages | Use case |
|---|---|---|
| `minimal` | load_tools, query_loop | Quick experiments |
| `standard` | prefetch through query_loop (8 stages) | Production use |
| `full` | All 10 stages including plugins and hooks | Maximum control |

---

## Tests

```bash
python -m unittest tests.test_harnesskit -v
```

78 tests covering catalog loading, permission logic, bootstrap pipelines, security scanning, config building, preset validation, and CLI commands.

---

## Roadmap

- [ ] YAML export support
- [ ] Web UI (Streamlit/Gradio)
- [ ] Template gallery for community-shared configs
- [ ] Runtime adapter for Claude Code / Cursor / Codex CLI
- [ ] GitHub Actions integration for automated config deployment

---

## License

This project is part of the [claw-code](https://github.com/kasparovabi/claw-code) repository.
