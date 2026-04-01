"""Tests for HarnessKit Claude Code hook integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harnesskit.hooks.enforcer import (
    find_config,
    load_policy_from_config,
    handle_pre_tool_use,
    handle_post_tool_use,
    handle_session_start,
    PreToolUseResult,
    PostToolUseResult,
    _resolve_tool_name,
)
from harnesskit.hooks.installer import (
    install_hooks,
    uninstall_hooks,
    HOOK_SETTINGS_FRAGMENT,
    _is_harnesskit_entry,
    _merge_hook_settings,
    _remove_harnesskit_hooks,
)
from harnesskit.presets import PRESET_CONFIGS


class _TempProjectMixin:
    """Create a temp dir with a .harnesskit.json for testing."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self._tmpdir.name)
        config = PRESET_CONFIGS["dev-assistant"]()
        config_path = self.project_dir / ".harnesskit.json"
        config_path.write_text(config.to_json(), encoding="utf-8")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _event(self, tool_name: str, tool_input: dict | None = None, **extra) -> dict:
        event = {
            "tool_name": tool_name,
            "tool_input": tool_input or {},
            "cwd": str(self.project_dir),
        }
        event.update(extra)
        return event


# ===================================================================
# Tool name mapping tests
# ===================================================================

class TestToolNameMapping(unittest.TestCase):

    def test_bash_maps_to_bashtool(self):
        names = _resolve_tool_name("Bash")
        self.assertIn("Bash", names)
        self.assertIn("BashTool", names)

    def test_edit_maps_to_fileedittool(self):
        names = _resolve_tool_name("Edit")
        self.assertIn("FileEditTool", names)

    def test_unknown_tool_returns_self(self):
        names = _resolve_tool_name("SomethingNew")
        self.assertEqual(names, ["SomethingNew"])

    def test_full_name_maps_back_to_short(self):
        names = _resolve_tool_name("BashTool")
        self.assertIn("BashTool", names)
        self.assertIn("Bash", names)


# ===================================================================
# Config loading tests
# ===================================================================

class TestConfigLoading(_TempProjectMixin, unittest.TestCase):

    def test_find_config_in_project_root(self):
        path = find_config(str(self.project_dir))
        self.assertIsNotNone(path)
        self.assertEqual(path.name, ".harnesskit.json")

    def test_find_config_from_subdirectory(self):
        sub = self.project_dir / "src" / "deep"
        sub.mkdir(parents=True)
        path = find_config(str(sub))
        self.assertIsNotNone(path)

    def test_find_config_returns_none(self):
        with tempfile.TemporaryDirectory() as empty:
            path = find_config(empty)
            self.assertIsNone(path)

    def test_load_policy(self):
        config_path = find_config(str(self.project_dir))
        policy = load_policy_from_config(config_path)
        self.assertTrue(policy.is_allowed("BashTool"))


# ===================================================================
# PreToolUse handler tests
# ===================================================================

class TestPreToolUse(_TempProjectMixin, unittest.TestCase):

    def test_allowed_tool_bash(self):
        result = handle_pre_tool_use(self._event("Bash", {"command": "ls"}))
        self.assertEqual(result.decision, "allow")

    def test_allowed_tool_read(self):
        result = handle_pre_tool_use(self._event("Read", {"file_path": "foo.py"}))
        self.assertEqual(result.decision, "allow")

    def test_allowed_tool_grep(self):
        result = handle_pre_tool_use(self._event("Grep", {"pattern": "foo"}))
        self.assertEqual(result.decision, "allow")

    def test_denied_mcp_tool(self):
        result = handle_pre_tool_use(self._event("mcp_server"))
        self.assertEqual(result.decision, "deny")
        self.assertIn("MCP", result.reason)

    def test_dangerous_rm_rf(self):
        result = handle_pre_tool_use(self._event("Bash", {"command": "rm -rf /"}))
        self.assertEqual(result.decision, "deny")
        self.assertIn("Dangerous", result.reason)

    def test_dangerous_fork_bomb(self):
        result = handle_pre_tool_use(self._event("Bash", {"command": ":(){:|:&};:"}))
        self.assertEqual(result.decision, "deny")

    def test_dangerous_dd(self):
        result = handle_pre_tool_use(self._event("Bash", {"command": "dd if=/dev/zero of=/dev/sda"}))
        self.assertEqual(result.decision, "deny")

    def test_secret_in_file_write(self):
        result = handle_pre_tool_use(self._event(
            "Write",
            {"file_path": "config.py", "content": "KEY = sk-ant-abcdefghijklmnopqrstuvwxyz"},
        ))
        self.assertEqual(result.decision, "deny")
        self.assertIn("secret", result.reason.lower())

    def test_secret_in_file_edit(self):
        result = handle_pre_tool_use(self._event(
            "Edit",
            {"file_path": "app.py", "new_string": "token = ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"},
        ))
        self.assertEqual(result.decision, "deny")

    def test_protected_file_env(self):
        result = handle_pre_tool_use(self._event("Edit", {"file_path": ".env.local"}))
        self.assertEqual(result.decision, "ask")
        self.assertIn("protected", result.reason.lower())

    def test_protected_file_credentials(self):
        result = handle_pre_tool_use(self._event("Read", {"file_path": "credentials.json"}))
        self.assertEqual(result.decision, "ask")

    def test_safe_file_write(self):
        result = handle_pre_tool_use(self._event(
            "Write",
            {"file_path": "main.py", "content": "print('hello')"},
        ))
        self.assertEqual(result.decision, "allow")

    def test_no_config_allows_all(self):
        with tempfile.TemporaryDirectory() as empty:
            result = handle_pre_tool_use({
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "cwd": empty,
            })
            self.assertEqual(result.decision, "allow")

    def test_result_to_hook_output_allow(self):
        result = PreToolUseResult(decision="allow")
        output = result.to_hook_output()
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"],
            "allow",
        )

    def test_result_to_hook_output_deny(self):
        result = PreToolUseResult(decision="deny", reason="blocked")
        output = result.to_hook_output()
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecisionReason"],
            "blocked",
        )


# ===================================================================
# PostToolUse handler tests
# ===================================================================

class TestPostToolUse(_TempProjectMixin, unittest.TestCase):

    def test_normal_result_allows(self):
        result = handle_post_tool_use(self._event(
            "Bash",
            {"command": "ls"},
            tool_result={"success": True, "output": "file1.py file2.py"},
        ))
        self.assertEqual(result.decision, "allow")

    def test_secret_in_result_blocks(self):
        result = handle_post_tool_use(self._event(
            "Bash",
            {"command": "cat config"},
            tool_result={"output": "API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz"},
        ))
        self.assertEqual(result.decision, "block")
        self.assertIn("secret", result.reason.lower())

    def test_empty_result_allows(self):
        result = handle_post_tool_use(self._event("Bash", {"command": "true"}))
        self.assertEqual(result.decision, "allow")

    def test_result_to_hook_output_block(self):
        result = PostToolUseResult(decision="block", reason="leaked secret")
        output = result.to_hook_output()
        self.assertEqual(output["decision"], "block")

    def test_result_to_hook_output_allow(self):
        result = PostToolUseResult(decision="allow")
        output = result.to_hook_output()
        self.assertEqual(output, {})


# ===================================================================
# SessionStart handler tests
# ===================================================================

class TestSessionStart(_TempProjectMixin, unittest.TestCase):

    def test_with_config(self):
        result = handle_session_start({"cwd": str(self.project_dir)})
        self.assertIn("additionalContext", result)
        self.assertIn("dev-assistant", result["additionalContext"])

    def test_without_config(self):
        with tempfile.TemporaryDirectory() as empty:
            result = handle_session_start({"cwd": empty})
            self.assertEqual(result, {})


# ===================================================================
# Installer tests
# ===================================================================

class TestInstaller(unittest.TestCase):

    def test_install_creates_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            actions = install_hooks(tmpdir)
            hooks_dir = Path(tmpdir) / ".claude" / "hooks"
            self.assertTrue(hooks_dir.is_dir())
            self.assertTrue((hooks_dir / "harnesskit-pre-tool-use.sh").is_file())
            self.assertTrue((hooks_dir / "harnesskit-post-tool-use.sh").is_file())
            self.assertTrue((hooks_dir / "harnesskit-session-start.sh").is_file())

    def test_install_creates_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_hooks(tmpdir)
            settings = Path(tmpdir) / ".claude" / "settings.json"
            self.assertTrue(settings.is_file())
            data = json.loads(settings.read_text())
            self.assertIn("hooks", data)
            self.assertIn("PreToolUse", data["hooks"])
            self.assertIn("PostToolUse", data["hooks"])
            self.assertIn("SessionStart", data["hooks"])

    def test_install_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Path(tmpdir) / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text(json.dumps({
                "some_key": "some_value",
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-hook.sh"}]}
                    ]
                }
            }))
            install_hooks(tmpdir)
            data = json.loads(settings.read_text())
            self.assertEqual(data["some_key"], "some_value")
            # Should have both the original and HarnessKit hooks
            self.assertGreater(len(data["hooks"]["PreToolUse"]), 1)

    def test_install_scripts_are_executable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_hooks(tmpdir)
            hooks_dir = Path(tmpdir) / ".claude" / "hooks"
            for f in hooks_dir.iterdir():
                if f.suffix == ".sh":
                    import os
                    self.assertTrue(os.access(f, os.X_OK))

    def test_uninstall_removes_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_hooks(tmpdir)
            actions = uninstall_hooks(tmpdir)
            hooks_dir = Path(tmpdir) / ".claude" / "hooks"
            self.assertFalse((hooks_dir / "harnesskit-pre-tool-use.sh").exists())
            self.assertFalse((hooks_dir / "harnesskit-post-tool-use.sh").exists())

    def test_uninstall_cleans_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install_hooks(tmpdir)
            uninstall_hooks(tmpdir)
            settings = Path(tmpdir) / ".claude" / "settings.json"
            data = json.loads(settings.read_text())
            self.assertNotIn("hooks", data)

    def test_uninstall_preserves_other_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-hook.sh"}]}
                    ]
                }
            }))
            install_hooks(tmpdir)
            uninstall_hooks(tmpdir)
            data = json.loads(settings_path.read_text())
            self.assertIn("hooks", data)
            self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)
            self.assertIn("my-hook.sh", data["hooks"]["PreToolUse"][0]["hooks"][0]["command"])

    def test_is_harnesskit_entry(self):
        self.assertTrue(_is_harnesskit_entry({
            "hooks": [{"type": "command", "command": "harnesskit-hook.sh"}]
        }))
        self.assertTrue(_is_harnesskit_entry({
            "hooks": [{"type": "command", "command": "foo.sh", "statusMessage": "HarnessKit: checking"}]
        }))
        self.assertFalse(_is_harnesskit_entry({
            "hooks": [{"type": "command", "command": "other-hook.sh"}]
        }))

    def test_idempotent_install(self):
        """Installing twice should not duplicate hooks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            install_hooks(tmpdir)
            install_hooks(tmpdir)
            settings = Path(tmpdir) / ".claude" / "settings.json"
            data = json.loads(settings.read_text())
            self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)


# ===================================================================
# CLI integration tests
# ===================================================================

class TestCLIHookCommands(unittest.TestCase):

    def test_install_command(self):
        from harnesskit.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            ret = main(["install", "-p", tmpdir])
            self.assertEqual(ret, 0)
            self.assertTrue((Path(tmpdir) / ".claude" / "settings.json").is_file())

    def test_uninstall_command(self):
        from harnesskit.cli import main
        with tempfile.TemporaryDirectory() as tmpdir:
            main(["install", "-p", tmpdir])
            ret = main(["uninstall", "-p", tmpdir])
            self.assertEqual(ret, 0)


# ===================================================================
# Audit log tests
# ===================================================================

class TestAuditLog(_TempProjectMixin, unittest.TestCase):

    def test_pre_tool_use_creates_log(self):
        import os
        log_dir = self.project_dir / "logs"
        os.environ["HARNESSKIT_LOG_DIR"] = str(log_dir)
        try:
            handle_pre_tool_use(self._event("Bash", {"command": "ls"}))
            log_files = list(log_dir.glob("audit-*.jsonl"))
            self.assertGreater(len(log_files), 0)
            content = log_files[0].read_text()
            entry = json.loads(content.strip().split("\n")[0])
            self.assertEqual(entry["event"], "PreToolUse")
        finally:
            os.environ.pop("HARNESSKIT_LOG_DIR", None)


# ===================================================================
# All presets with enforcer
# ===================================================================

class TestPresetsWithEnforcer(unittest.TestCase):

    def test_every_preset_loads_as_policy(self):
        """Every preset config must be loadable as an enforcer policy."""
        for name, factory in PRESET_CONFIGS.items():
            config = factory()
            with tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / ".harnesskit.json"
                path.write_text(config.to_json())
                policy = load_policy_from_config(path)
                # Basic sanity: the policy should have rules
                self.assertGreater(len(policy.rules), 0, f"Preset {name} has no rules")


if __name__ == "__main__":
    unittest.main()
