"""Comprehensive test suite for the HarnessKit package."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harnesskit.catalog import CatalogEntry, Catalog, load_catalog, _infer_category, _TOOL_CATEGORY_RULES
from harnesskit.permissions import (
    PermissionRule,
    PermissionPolicy,
    preset_restrictive,
    preset_standard,
    preset_permissive,
    preset_research,
    PRESETS,
)
from harnesskit.bootstrap import (
    Stage,
    BootstrapPipeline,
    STAGE_LIBRARY,
    PIPELINE_PRESETS,
    preset_minimal,
    preset_standard as bootstrap_standard,
    preset_full,
)
from harnesskit.security import (
    scan_for_secrets,
    sanitise_name,
    contains_shell_injection,
    audit_config,
    AuditReport,
)
from harnesskit.config import (
    ModelConfig,
    HarnessConfig,
    ConfigBuilder,
)
from harnesskit.presets import PRESET_CONFIGS
from harnesskit.cli import build_parser, main


# ===================================================================
# Catalog tests
# ===================================================================

class TestCatalog(unittest.TestCase):

    def test_load_catalog_returns_entries(self):
        catalog = load_catalog()
        self.assertGreater(len(catalog.entries), 100)

    def test_tools_and_commands_partition(self):
        catalog = load_catalog()
        total = len(catalog.tools) + len(catalog.commands)
        self.assertEqual(total, len(catalog.entries))

    def test_categories_not_empty(self):
        catalog = load_catalog()
        self.assertGreater(len(catalog.categories), 5)

    def test_search_returns_results(self):
        catalog = load_catalog()
        results = catalog.search("Bash")
        self.assertGreater(len(results), 0)
        self.assertTrue(any("Bash" in e.name for e in results))

    def test_search_case_insensitive(self):
        catalog = load_catalog()
        upper = catalog.search("BASH")
        lower = catalog.search("bash")
        self.assertEqual(len(upper), len(lower))

    def test_by_category(self):
        catalog = load_catalog()
        shells = catalog.by_category("shell")
        self.assertGreater(len(shells), 0)
        for e in shells:
            self.assertEqual(e.category, "shell")

    def test_select_by_names(self):
        catalog = load_catalog()
        selected = catalog.select(["BashTool", "GrepTool"])
        names = {e.name for e in selected}
        self.assertIn("BashTool", names)
        self.assertIn("GrepTool", names)

    def test_unique_names_deduplicates(self):
        catalog = load_catalog()
        names = catalog.unique_names()
        self.assertEqual(len(names), len(set(names)))

    def test_catalog_entry_matches(self):
        entry = CatalogEntry("BashTool", "tool", "tools/BashTool.ts", "Shell", "shell")
        self.assertTrue(entry.matches("bash"))
        self.assertTrue(entry.matches("shell"))
        self.assertFalse(entry.matches("zzzzz"))

    def test_infer_category_fallback(self):
        cat = _infer_category("unknown_thing", "some/path.ts", _TOOL_CATEGORY_RULES)
        self.assertEqual(cat, "general")


# ===================================================================
# Permission tests
# ===================================================================

class TestPermissions(unittest.TestCase):

    def test_rule_validation_rejects_empty(self):
        with self.assertRaises(ValueError):
            PermissionRule("", "allow")

    def test_rule_validation_rejects_shell_chars(self):
        with self.assertRaises(ValueError):
            PermissionRule("foo;bar", "allow")

    def test_rule_exact_match(self):
        rule = PermissionRule("BashTool", "deny")
        self.assertTrue(rule.matches("BashTool"))
        self.assertTrue(rule.matches("bashtool"))
        self.assertFalse(rule.matches("BashToolExtra"))

    def test_rule_prefix_match(self):
        rule = PermissionRule("mcp*", "deny")
        self.assertTrue(rule.matches("mcp_server"))
        self.assertTrue(rule.matches("MCP_anything"))
        self.assertFalse(rule.matches("not_mcp"))

    def test_policy_first_match_wins(self):
        policy = PermissionPolicy(
            rules=(
                PermissionRule("BashTool", "deny", "blocked"),
                PermissionRule("BashTool", "allow", "should not reach"),
            ),
            default_action="allow",
        )
        self.assertFalse(policy.is_allowed("BashTool"))

    def test_policy_default_applies(self):
        policy = PermissionPolicy(rules=(), default_action="allow")
        self.assertTrue(policy.is_allowed("anything"))

        policy_deny = PermissionPolicy(rules=(), default_action="deny")
        self.assertFalse(policy_deny.is_allowed("anything"))

    def test_blocked_names(self):
        policy = preset_restrictive()
        blocked = policy.blocked_names(["BashTool", "FileReadTool", "GrepTool"])
        self.assertIn("BashTool", blocked)
        self.assertNotIn("FileReadTool", blocked)

    def test_allowed_names(self):
        policy = preset_standard()
        allowed = policy.allowed_names(["BashTool", "FileReadTool", "GrepTool"])
        self.assertIn("FileReadTool", allowed)
        self.assertIn("BashTool", allowed)

    def test_add_rule_returns_new_policy(self):
        policy = PermissionPolicy()
        new_policy = policy.add_rule(PermissionRule("BashTool", "allow"))
        self.assertEqual(len(new_policy.rules), 1)
        self.assertEqual(len(policy.rules), 0)  # Original unchanged

    def test_all_presets_load(self):
        for name, factory in PRESETS.items():
            policy = factory()
            self.assertIsInstance(policy, PermissionPolicy)
            self.assertGreater(len(policy.rules), 0)

    def test_policy_as_dict(self):
        policy = preset_standard()
        d = policy.as_dict()
        self.assertIn("default_action", d)
        self.assertIn("rules", d)
        self.assertIsInstance(d["rules"], list)


# ===================================================================
# Bootstrap tests
# ===================================================================

class TestBootstrap(unittest.TestCase):

    def test_stage_validation_empty_name(self):
        with self.assertRaises(ValueError):
            Stage("", "load", "desc", 0)

    def test_stage_validation_bad_kind(self):
        with self.assertRaises(ValueError):
            Stage("test", "invalid_kind", "desc", 0)

    def test_stage_validation_negative_order(self):
        with self.assertRaises(ValueError):
            Stage("test", "load", "desc", -1)

    def test_pipeline_add_stage_inserts_sorted(self):
        pipeline = preset_minimal()
        new_stage = Stage("guard", "guard", "test guard", 5)
        new_pipeline = pipeline.add_stage(new_stage)
        self.assertEqual(new_pipeline.stages[0].name, "guard")

    def test_pipeline_remove_stage(self):
        pipeline = bootstrap_standard()
        count_before = len(pipeline.stages)
        new_pipeline = pipeline.remove_stage("prefetch")
        self.assertEqual(len(new_pipeline.stages), count_before - 1)

    def test_pipeline_as_dict(self):
        pipeline = preset_minimal()
        d = pipeline.as_dict()
        self.assertIsInstance(d, list)
        self.assertTrue(all("name" in s for s in d))

    def test_stage_library_complete(self):
        self.assertGreater(len(STAGE_LIBRARY), 5)
        for name, stage in STAGE_LIBRARY.items():
            self.assertEqual(stage.name, name)

    def test_all_pipeline_presets_load(self):
        for name, factory in PIPELINE_PRESETS.items():
            pipeline = factory()
            self.assertIsInstance(pipeline, BootstrapPipeline)
            self.assertGreater(len(pipeline.stages), 0)

    def test_full_preset_includes_all_stages(self):
        pipeline = preset_full()
        self.assertEqual(len(pipeline.stages), len(STAGE_LIBRARY))


# ===================================================================
# Security tests
# ===================================================================

class TestSecurity(unittest.TestCase):

    def test_sanitise_name_valid(self):
        self.assertEqual(sanitise_name("my-agent"), "my-agent")
        self.assertEqual(sanitise_name("  agent_v2  "), "agent_v2")

    def test_sanitise_name_rejects_empty(self):
        with self.assertRaises(ValueError):
            sanitise_name("")

    def test_sanitise_name_rejects_special_chars(self):
        with self.assertRaises(ValueError):
            sanitise_name("my agent!")

    def test_sanitise_name_rejects_starts_with_number(self):
        with self.assertRaises(ValueError):
            sanitise_name("123agent")

    def test_sanitise_name_rejects_long(self):
        with self.assertRaises(ValueError):
            sanitise_name("a" * 200)

    def test_shell_injection_detected(self):
        self.assertTrue(contains_shell_injection("ls; rm -rf /"))
        self.assertTrue(contains_shell_injection("$(whoami)"))
        self.assertTrue(contains_shell_injection("foo | bar"))
        self.assertTrue(contains_shell_injection("foo`id`"))

    def test_shell_injection_clean(self):
        self.assertFalse(contains_shell_injection("hello-world"))
        self.assertFalse(contains_shell_injection("my_agent_v2"))

    def test_secret_detection_aws(self):
        data = {"key": "AKIAIOSFODNN7EXAMPLE"}
        findings = scan_for_secrets(data)
        self.assertGreater(len(findings), 0)
        self.assertTrue(any("AWS" in f.pattern_name for f in findings))

    def test_secret_detection_github_token(self):
        data = {"token": "ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"}
        findings = scan_for_secrets(data)
        self.assertGreater(len(findings), 0)

    def test_secret_detection_anthropic_key(self):
        data = {"api_key": "sk-ant-abcdefghijklmnopqrstuvwxyz"}
        findings = scan_for_secrets(data)
        self.assertGreater(len(findings), 0)

    def test_secret_detection_nested(self):
        data = {"config": {"nested": {"deep": "sk-ant-abcdefghijklmnopqrstuvwxyz"}}}
        findings = scan_for_secrets(data)
        self.assertGreater(len(findings), 0)
        self.assertIn("config.nested.deep", findings[0].field_path)

    def test_secret_detection_in_lists(self):
        data = {"tokens": ["safe_value", "ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"]}
        findings = scan_for_secrets(data)
        self.assertGreater(len(findings), 0)

    def test_secret_masking(self):
        data = {"key": "sk-ant-abcdefghijklmnopqrstuvwxyz"}
        findings = scan_for_secrets(data)
        for f in findings:
            self.assertIn("****", f.masked_value)
            self.assertNotEqual(f.masked_value, data["key"])

    def test_no_false_positives_on_clean_data(self):
        data = {"name": "my-agent", "tools": ["BashTool", "GrepTool"]}
        findings = scan_for_secrets(data)
        self.assertEqual(len(findings), 0)

    def test_audit_config_safe(self):
        config = {
            "permissions": {
                "default_action": "deny",
                "rules": [{"target": "FileReadTool", "action": "allow"}],
            },
            "bootstrap": {"stages": [{"name": "trust_gate"}, {"name": "environment_guard"}]},
            "model": {"name": "claude-sonnet-4-6"},
        }
        report = audit_config(config)
        self.assertTrue(report.passed)
        self.assertGreater(report.score, 80)

    def test_audit_config_dangerous(self):
        config = {
            "permissions": {
                "default_action": "allow",
                "rules": [{"target": "BashTool", "action": "allow"}],
            },
            "bootstrap": {"stages": []},
            "api_key": "sk-ant-abcdefghijklmnopqrstuvwxyz",
        }
        report = audit_config(config)
        self.assertFalse(report.passed)
        self.assertLess(report.score, 50)

    def test_audit_report_markdown(self):
        report = AuditReport(findings=())
        md = report.as_markdown()
        self.assertIn("100/100", md)


# ===================================================================
# Config tests
# ===================================================================

class TestConfig(unittest.TestCase):

    def test_model_config_validation(self):
        with self.assertRaises(ValueError):
            ModelConfig(max_tokens=0)
        with self.assertRaises(ValueError):
            ModelConfig(temperature=3.0)

    def test_harness_config_validates_name(self):
        with self.assertRaises(ValueError):
            HarnessConfig(project_name="invalid name!")

    def test_config_to_json(self):
        config = HarnessConfig(project_name="test-project")
        j = config.to_json()
        data = json.loads(j)
        self.assertEqual(data["project_name"], "test-project")
        self.assertIn("harnesskit_version", data)
        self.assertIn("generated_at", data)

    def test_config_export_json(self):
        config = HarnessConfig(project_name="test-project")
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            config.export_json(path)
            data = json.loads(path.read_text())
            self.assertEqual(data["project_name"], "test-project")
        finally:
            path.unlink(missing_ok=True)

    def test_config_audit(self):
        config = HarnessConfig(project_name="test-project")
        report = config.audit()
        self.assertIsInstance(report, AuditReport)

    def test_config_summary(self):
        config = HarnessConfig(project_name="test-project")
        summary = config.summary()
        self.assertIn("test-project", summary)
        self.assertIn("Safety score", summary)

    def test_builder_basic(self):
        config = ConfigBuilder("my-agent").build()
        self.assertEqual(config.project_name, "my-agent")

    def test_builder_full(self):
        config = (
            ConfigBuilder("full-agent")
            .description("A full test agent")
            .add_tools(["BashTool", "GrepTool"])
            .add_commands(["commit", "branch"])
            .set_permission_preset("standard")
            .set_bootstrap_preset("standard")
            .set_model("claude-sonnet-4-6", provider="anthropic")
            .build()
        )
        self.assertEqual(config.project_name, "full-agent")
        self.assertEqual(len(config.tools), 2)
        self.assertEqual(len(config.commands), 2)
        self.assertEqual(config.model.name, "claude-sonnet-4-6")

    def test_builder_deduplicates_tools(self):
        config = (
            ConfigBuilder("dedup-test")
            .add_tools(["BashTool", "BashTool", "GrepTool"])
            .build()
        )
        self.assertEqual(len(config.tools), 2)

    def test_builder_rejects_bad_name(self):
        with self.assertRaises(ValueError):
            ConfigBuilder("bad name!")

    def test_builder_rejects_bad_tool_name(self):
        with self.assertRaises(ValueError):
            ConfigBuilder("test").add_tools(["valid", "in valid!"])

    def test_builder_unknown_permission_preset(self):
        with self.assertRaises(ValueError):
            ConfigBuilder("test").set_permission_preset("nonexistent")

    def test_builder_unknown_bootstrap_preset(self):
        with self.assertRaises(ValueError):
            ConfigBuilder("test").set_bootstrap_preset("nonexistent")

    def test_builder_add_tools_by_category(self):
        config = (
            ConfigBuilder("cat-test")
            .add_tools_by_category("shell")
            .build()
        )
        self.assertGreater(len(config.tools), 0)


# ===================================================================
# Preset tests
# ===================================================================

class TestPresets(unittest.TestCase):

    def test_all_presets_load(self):
        for name, factory in PRESET_CONFIGS.items():
            config = factory()
            self.assertIsInstance(config, HarnessConfig)
            self.assertTrue(config.project_name)

    def test_all_presets_export_valid_json(self):
        for name, factory in PRESET_CONFIGS.items():
            config = factory()
            data = json.loads(config.to_json())
            self.assertIn("harnesskit_version", data)
            self.assertIn("permissions", data)
            self.assertIn("bootstrap", data)

    def test_all_presets_pass_audit(self):
        for name, factory in PRESET_CONFIGS.items():
            config = factory()
            report = config.audit()
            self.assertTrue(
                report.passed,
                f"Preset '{name}' failed audit with score {report.score}",
            )

    def test_safe_sandbox_has_no_shell(self):
        config = PRESET_CONFIGS["safe-sandbox"]()
        self.assertNotIn("BashTool", config.tools)

    def test_dev_assistant_has_shell(self):
        config = PRESET_CONFIGS["dev-assistant"]()
        self.assertIn("BashTool", config.tools)

    def test_research_agent_no_file_write(self):
        config = PRESET_CONFIGS["research-agent"]()
        self.assertNotIn("FileEditTool", config.tools)
        self.assertNotIn("FileWriteTool", config.tools)


# ===================================================================
# CLI tests
# ===================================================================

class TestCLI(unittest.TestCase):

    def test_presets_command(self):
        ret = main(["presets"])
        self.assertEqual(ret, 0)

    def test_catalog_categories(self):
        ret = main(["catalog", "categories"])
        self.assertEqual(ret, 0)

    def test_catalog_tools(self):
        ret = main(["catalog", "tools", "-l", "5"])
        self.assertEqual(ret, 0)

    def test_catalog_commands(self):
        ret = main(["catalog", "commands", "-l", "5"])
        self.assertEqual(ret, 0)

    def test_catalog_search(self):
        ret = main(["catalog", "-q", "bash"])
        self.assertEqual(ret, 0)

    def test_stages_command(self):
        ret = main(["stages"])
        self.assertEqual(ret, 0)

    def test_preset_export(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ret = main(["preset", "dev-assistant", "-o", path])
            self.assertEqual(ret, 0)
            data = json.loads(Path(path).read_text())
            self.assertEqual(data["project_name"], "dev-assistant")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_audit_command(self):
        config = PRESET_CONFIGS["dev-assistant"]()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write(config.to_json())
            path = f.name
        try:
            ret = main(["audit", path])
            self.assertEqual(ret, 0)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_audit_nonexistent_file(self):
        ret = main(["audit", "/nonexistent/file.json"])
        self.assertEqual(ret, 1)

    def test_unknown_preset(self):
        ret = main(["preset", "nonexistent"])
        self.assertEqual(ret, 1)

    def test_no_command_shows_help(self):
        ret = main([])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
