"""Security utilities for HarnessKit configurations.

Provides input sanitisation, secret detection, configuration auditing,
and safety scoring so that exported configs can be reviewed before deployment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII)),
    ("AWS secret key", re.compile(r"[A-Za-z0-9/+=]{40}", re.ASCII)),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}", re.ASCII)),
    ("Generic API key", re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9\-_.]{20,}", re.IGNORECASE)),
    ("Bearer token", re.compile(r"Bearer\s+[A-Za-z0-9\-_.~+/]+=*", re.ASCII)),
    ("Private key header", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----")),
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}", re.ASCII)),
    ("OpenAI API key", re.compile(r"sk-[A-Za-z0-9]{20,}", re.ASCII)),
    ("Slack token", re.compile(r"xox[bporas]-[A-Za-z0-9\-]+", re.ASCII)),
    ("Generic secret assignment", re.compile(r"(?:secret|password|passwd|token)\s*[:=]\s*['\"]?[^\s'\"]{8,}", re.IGNORECASE)),
]


@dataclass(frozen=True)
class SecretFinding:
    """A potential secret detected in a configuration value."""
    field_path: str
    pattern_name: str
    masked_value: str


def scan_for_secrets(data: dict, _path: str = "") -> list[SecretFinding]:
    """Recursively scan *data* dict for values that look like secrets.

    Returns a list of findings.  Values are masked in the output so that
    the findings themselves do not leak sensitive material.
    """
    findings: list[SecretFinding] = []
    for key, value in data.items():
        current_path = f"{_path}.{key}" if _path else key
        if isinstance(value, dict):
            findings.extend(scan_for_secrets(value, current_path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    findings.extend(scan_for_secrets(item, f"{current_path}[{i}]"))
                elif isinstance(item, str):
                    findings.extend(_scan_string(item, f"{current_path}[{i}]"))
        elif isinstance(value, str):
            findings.extend(_scan_string(value, current_path))
    return findings


def _scan_string(value: str, path: str) -> list[SecretFinding]:
    results: list[SecretFinding] = []
    for pattern_name, regex in _SECRET_PATTERNS:
        if regex.search(value):
            masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
            results.append(SecretFinding(
                field_path=path,
                pattern_name=pattern_name,
                masked_value=masked,
            ))
    return results


# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------

_SHELL_META = re.compile(r"[;&|`$(){}!\\\n\r]")
_MAX_NAME_LENGTH = 128
_VALID_NAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]*$")


def sanitise_name(name: str) -> str:
    """Return *name* stripped and validated, or raise ``ValueError``.

    Names must start with a letter and contain only alphanumerics,
    underscores, and hyphens.  Maximum length is 128 characters.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Name must not be empty.")
    if len(cleaned) > _MAX_NAME_LENGTH:
        raise ValueError(f"Name exceeds {_MAX_NAME_LENGTH} characters.")
    if not _VALID_NAME.match(cleaned):
        raise ValueError(
            f"Invalid name {cleaned!r}. "
            "Names must start with a letter and contain only [a-zA-Z0-9_-]."
        )
    return cleaned


def contains_shell_injection(value: str) -> bool:
    """Return ``True`` if *value* contains shell meta-characters."""
    return bool(_SHELL_META.search(value))


# ---------------------------------------------------------------------------
# Configuration safety audit
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditFinding:
    severity: str  # "info", "warning", "critical"
    category: str
    message: str


@dataclass(frozen=True)
class AuditReport:
    findings: tuple[AuditFinding, ...]

    @property
    def score(self) -> int:
        """Safety score from 0 (dangerous) to 100 (very safe)."""
        penalty = 0
        for f in self.findings:
            if f.severity == "critical":
                penalty += 30
            elif f.severity == "warning":
                penalty += 10
            elif f.severity == "info":
                penalty += 2
        return max(0, 100 - penalty)

    @property
    def passed(self) -> bool:
        return not any(f.severity == "critical" for f in self.findings)

    def as_markdown(self) -> str:
        lines = [f"# Security Audit Report", f"", f"**Safety Score: {self.score}/100**", ""]
        if not self.findings:
            lines.append("No issues found.")
            return "\n".join(lines)
        for f in self.findings:
            icon = {"info": "INFO", "warning": "WARN", "critical": "CRIT"}[f.severity]
            lines.append(f"- [{icon}] {f.category}: {f.message}")
        return "\n".join(lines)


def audit_config(config: dict) -> AuditReport:
    """Run a safety audit on a serialised HarnessKit configuration dict."""
    findings: list[AuditFinding] = []

    # 1. Check for embedded secrets
    secrets = scan_for_secrets(config)
    for s in secrets:
        findings.append(AuditFinding(
            severity="critical",
            category="secrets",
            message=f"Potential {s.pattern_name} found at {s.field_path}",
        ))

    # 2. Check permission policy
    policy = config.get("permissions", {})
    default_action = policy.get("default_action", "deny")
    if default_action == "allow":
        findings.append(AuditFinding(
            severity="warning",
            category="permissions",
            message="Default permission action is 'allow'. Consider 'deny' for safer defaults.",
        ))
    rules = policy.get("rules", [])
    if not rules:
        findings.append(AuditFinding(
            severity="warning",
            category="permissions",
            message="No explicit permission rules defined.",
        ))

    # 3. Check for shell access
    for rule in rules:
        if rule.get("target", "").lower() in ("bashtool", "shelltool"):
            if rule.get("action") == "allow":
                findings.append(AuditFinding(
                    severity="warning",
                    category="shell-access",
                    message=f"Shell tool '{rule['target']}' is explicitly allowed. "
                            "Ensure this is intentional for your use case.",
                ))

    # 4. Check for MCP tools
    for rule in rules:
        target = rule.get("target", "").lower()
        if "mcp" in target and rule.get("action") == "allow":
            findings.append(AuditFinding(
                severity="info",
                category="mcp",
                message=f"MCP tool pattern '{rule['target']}' is allowed. "
                        "MCP tools connect to external services.",
            ))

    # 5. Check bootstrap pipeline
    pipeline = config.get("bootstrap", {}).get("stages", [])
    has_trust_gate = any(s.get("name") == "trust_gate" for s in pipeline)
    has_env_guard = any(s.get("name") == "environment_guard" for s in pipeline)
    if not has_trust_gate:
        findings.append(AuditFinding(
            severity="warning",
            category="bootstrap",
            message="No 'trust_gate' stage in bootstrap pipeline. "
                    "Agent will not verify workspace trust level.",
        ))
    if not has_env_guard:
        findings.append(AuditFinding(
            severity="info",
            category="bootstrap",
            message="No 'environment_guard' stage. "
                    "Environment validation will be skipped.",
        ))

    # 6. Check model configuration
    model = config.get("model", {})
    if not model.get("name"):
        findings.append(AuditFinding(
            severity="info",
            category="model",
            message="No model specified. Consumers must supply one at runtime.",
        ))

    return AuditReport(findings=tuple(findings))
