"""Comprehensive tests for Zoku."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from zoku.recorder import (
    Action, SessionTrace, summarise_input, summarise_response,
    record_action, record_prompt, load_all_traces,
    _zoku_dir, _traces_dir, _normalise_tool_name,
)
from zoku.detector import (
    detect_patterns, save_patterns, load_patterns,
    WorkflowPattern, _extract_subsequences, _is_contiguous_subset,
)
from zoku.hooks import (
    handle_post_tool_use, handle_stop, handle_session_start,
    handle_user_prompt_submit,
)
from zoku.installer import install, uninstall, _is_zoku_entry
from zoku.cli import main


class _TempProjectMixin:
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name)
        self._old_env = os.environ.get("ZOKU_DATA_DIR")
        os.environ["ZOKU_DATA_DIR"] = str(self.project / ".zoku")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("ZOKU_DATA_DIR", None)
        else:
            os.environ["ZOKU_DATA_DIR"] = self._old_env
        self._tmpdir.cleanup()

    def _post_event(self, tool, inp, session="s1", response=None):
        event = {"tool_name": tool, "tool_input": inp, "session_id": session, "cwd": str(self.project)}
        if response is not None:
            event["tool_response"] = response
        return event

    def _record_session(self, session_id, steps):
        for tool, inp in steps:
            record_action(self._post_event(tool, inp, session_id))


class TestAction(unittest.TestCase):
    def test_action_roundtrip(self):
        a = Action("Bash", "ls -la", "2026-01-01T00:00:00Z", "s1", True)
        d = a.to_dict()
        b = Action.from_dict(d)
        self.assertEqual(a.tool, b.tool)
        self.assertEqual(a.input_summary, b.input_summary)
        self.assertEqual(a.success, b.success)

    def test_action_with_response(self):
        a = Action("Bash", "ls", "t1", "s1", True, response_summary="exit:0", tool_use_id="tu_123", agent_id="agent_1")
        d = a.to_dict()
        b = Action.from_dict(d)
        self.assertEqual(b.response_summary, "exit:0")
        self.assertEqual(b.tool_use_id, "tu_123")
        self.assertEqual(b.agent_id, "agent_1")

    def test_action_compact_serialization(self):
        a = Action("Bash", "ls", "t1", "s1", True)
        d = a.to_dict()
        self.assertNotIn("response_summary", d)
        self.assertNotIn("tool_use_id", d)
        self.assertNotIn("agent_id", d)

    def test_session_trace_tool_sequence(self):
        trace = SessionTrace("s1", [
            Action("Grep", "pattern", "", "s1"),
            Action("Read", "file.py", "", "s1"),
            Action("Edit", "file.py", "", "s1"),
        ])
        self.assertEqual(trace.tool_sequence, ("Grep", "Read", "Edit"))

    def test_session_trace_jsonl_roundtrip(self):
        trace = SessionTrace("s1", [
            Action("Bash", "ls", "t1", "s1"),
            Action("Read", "f.py", "t2", "s1"),
        ])
        jsonl = trace.to_jsonl()
        restored = SessionTrace.from_jsonl(jsonl, "s1")
        self.assertEqual(len(restored.actions), 2)
        self.assertEqual(restored.actions[0].tool, "Bash")


class TestSummariseInput(unittest.TestCase):
    def test_bash(self):
        self.assertEqual(summarise_input("Bash", {"command": "ls -la"}), "ls -la")
    def test_read(self):
        self.assertEqual(summarise_input("Read", {"file_path": "foo.py"}), "foo.py")
    def test_edit(self):
        self.assertIn("edit:", summarise_input("Edit", {"file_path": "bar.py"}))
    def test_write(self):
        self.assertIn("write:", summarise_input("Write", {"file_path": "new.py"}))
    def test_grep(self):
        self.assertIn("grep:", summarise_input("Grep", {"pattern": "TODO"}))
    def test_glob(self):
        self.assertIn("glob:", summarise_input("Glob", {"pattern": "*.py"}))
    def test_agent(self):
        self.assertIn("agent:", summarise_input("Agent", {"description": "research"}))
    def test_web_search(self):
        self.assertIn("search:", summarise_input("WebSearch", {"query": "python"}))
    def test_unknown_tool(self):
        result = summarise_input("FooTool", {"a": 1, "b": 2})
        self.assertIn("FooTool", result)
    def test_truncation(self):
        long_cmd = "x" * 500
        result = summarise_input("Bash", {"command": long_cmd})
        self.assertLessEqual(len(result), 200)
    def test_mcp_tool(self):
        result = summarise_input("mcp__github__push_files", {"owner": "kasparovabi", "repo": "zoku"})
        self.assertIn("github:push_files", result)
    def test_mcp_tool_with_repo(self):
        result = summarise_input("mcp__github__create_pull_request", {"owner": "test"})
        self.assertIn("github:create_pull_request:test", result)


class TestSummariseResponse(unittest.TestCase):
    def test_bash_success(self):
        self.assertEqual(summarise_response("Bash", {"exitCode": 0}), "exit:0")
    def test_bash_failure(self):
        result = summarise_response("Bash", {"exitCode": 1, "stderr": "error: not found"})
        self.assertIn("exit:1", result)
        self.assertIn("not found", result)
    def test_success_tool(self):
        self.assertEqual(summarise_response("Edit", {"success": True}), "ok")
        self.assertEqual(summarise_response("Edit", {"success": False}), "failed")
    def test_empty_response(self):
        self.assertEqual(summarise_response("Bash", None), "")
        self.assertEqual(summarise_response("Bash", {}), "")
    def test_string_response(self):
        result = summarise_response("Read", "file contents here")
        self.assertEqual(result, "file contents here")


class TestNormaliseToolName(unittest.TestCase):
    def test_mcp_tool(self):
        self.assertEqual(_normalise_tool_name("mcp__github__push_files"), "github:push_files")
    def test_mcp_tool_with_uuid(self):
        result = _normalise_tool_name("mcp__e7ed62fd-e924-45de__gmail_send")
        self.assertEqual(result, "e7ed62fd-e924-45de:gmail_send")
    def test_regular_tool(self):
        self.assertEqual(_normalise_tool_name("Bash"), "Bash")
        self.assertEqual(_normalise_tool_name("Read"), "Read")


class TestRecording(_TempProjectMixin, unittest.TestCase):
    def test_record_creates_file(self):
        record_action(self._post_event("Bash", {"command": "ls"}))
        traces = load_all_traces()
        self.assertEqual(len(traces), 1)
        self.assertEqual(len(traces[0].actions), 1)

    def test_record_with_response(self):
        record_action(self._post_event("Bash", {"command": "npm test"}, response={"exitCode": 1, "stderr": "FAIL"}))
        traces = load_all_traces()
        action = traces[0].actions[0]
        self.assertFalse(action.success)
        self.assertIn("exit:1", action.response_summary)

    def test_record_mcp_tool(self):
        record_action(self._post_event("mcp__github__push_files", {"owner": "kasparovabi", "repo": "zoku"}))
        traces = load_all_traces()
        self.assertEqual(traces[0].actions[0].tool, "github:push_files")

    def test_multiple_actions_in_session(self):
        record_action(self._post_event("Bash", {"command": "ls"}, "s1"))
        record_action(self._post_event("Read", {"file_path": "a.py"}, "s1"))
        record_action(self._post_event("Edit", {"file_path": "a.py"}, "s1"))
        traces = load_all_traces()
        self.assertEqual(len(traces), 1)
        self.assertEqual(len(traces[0].actions), 3)

    def test_multiple_sessions(self):
        record_action(self._post_event("Bash", {"command": "ls"}, "s1"))
        record_action(self._post_event("Bash", {"command": "pwd"}, "s2"))
        traces = load_all_traces()
        self.assertEqual(len(traces), 2)

    def test_record_prompt(self):
        event = {"session_id": "s1", "prompt": "fix the bug in main.py", "cwd": str(self.project)}
        record_prompt(event)
        prompts_dir = self.project / ".zoku" / "prompts"
        files = list(prompts_dir.glob("*.jsonl"))
        self.assertEqual(len(files), 1)
        data = json.loads(files[0].read_text().strip())
        self.assertIn("fix the bug", data["prompt"])


class TestSubsequences(unittest.TestCase):
    def test_basic_extraction(self):
        seq = ("A", "B", "C", "D")
        subs = _extract_subsequences(seq, min_len=3, max_len=4)
        self.assertIn(("A", "B", "C"), subs)
        self.assertIn(("B", "C", "D"), subs)
        self.assertIn(("A", "B", "C", "D"), subs)
    def test_min_length_filter(self):
        seq = ("A", "B")
        subs = _extract_subsequences(seq, min_len=3)
        self.assertEqual(subs, [])
    def test_contiguous_subset(self):
        self.assertTrue(_is_contiguous_subset(("B", "C"), ("A", "B", "C", "D")))
        self.assertFalse(_is_contiguous_subset(("A", "C"), ("A", "B", "C", "D")))


class TestDetection(_TempProjectMixin, unittest.TestCase):
    def _standard_sessions(self):
        self._record_session("s1", [("Grep", {"pattern": "bug"}), ("Read", {"file_path": "a.py"}), ("Edit", {"file_path": "a.py"}), ("Bash", {"command": "pytest"}), ("Bash", {"command": "git commit"})])
        self._record_session("s2", [("Grep", {"pattern": "error"}), ("Read", {"file_path": "b.py"}), ("Edit", {"file_path": "b.py"}), ("Bash", {"command": "pytest"}), ("Bash", {"command": "git commit"})])
        self._record_session("s3", [("Read", {"file_path": "c.py"}), ("Edit", {"file_path": "c.py"}), ("Bash", {"command": "pytest"}), ("Bash", {"command": "git commit"})])

    def test_finds_patterns(self):
        self._standard_sessions()
        patterns = detect_patterns()
        self.assertGreater(len(patterns), 0)
    def test_pattern_has_correct_fields(self):
        self._standard_sessions()
        patterns = detect_patterns()
        p = patterns[0]
        self.assertGreater(p.occurrence_count, 1)
        self.assertGreater(p.length, 2)
        self.assertTrue(p.name)
    def test_most_frequent_first(self):
        self._standard_sessions()
        patterns = detect_patterns()
        if len(patterns) > 1:
            self.assertGreaterEqual(patterns[0].occurrence_count, patterns[1].occurrence_count)
    def test_no_patterns_from_one_session(self):
        self._record_session("s1", [("Bash", {"command": "ls"}), ("Read", {"file_path": "a.py"}), ("Edit", {"file_path": "a.py"})])
        patterns = detect_patterns()
        self.assertEqual(len(patterns), 0)
    def test_short_sessions_no_patterns(self):
        self._record_session("s1", [("Bash", {"command": "ls"})])
        self._record_session("s2", [("Bash", {"command": "pwd"})])
        patterns = detect_patterns()
        self.assertEqual(len(patterns), 0)
    def test_identical_sessions_detect(self):
        for sid in ("s1", "s2", "s3"):
            self._record_session(sid, [("Read", {"file_path": "x.py"}), ("Edit", {"file_path": "x.py"}), ("Bash", {"command": "test"})])
        patterns = detect_patterns()
        self.assertGreater(len(patterns), 0)
        self.assertEqual(patterns[0].occurrence_count, 3)
    def test_save_and_load_patterns(self):
        self._standard_sessions()
        patterns = detect_patterns()
        save_patterns(patterns)
        loaded = load_patterns()
        self.assertEqual(len(loaded), len(patterns))
        self.assertEqual(loaded[0].name, patterns[0].name)
    def test_pattern_name_generation(self):
        p = WorkflowPattern(steps=("Grep", "Read", "Edit", "Bash", "Bash"), occurrence_count=2, session_ids=("s1", "s2"), example_inputs=())
        self.assertEqual(p.name, "Grep -> Read -> Edit -> Bash")
    def test_pattern_roundtrip(self):
        p = WorkflowPattern(steps=("Read", "Edit"), occurrence_count=3, session_ids=("s1", "s2", "s3"), example_inputs=("a.py", "edit:a.py"))
        restored = WorkflowPattern.from_dict(p.to_dict())
        self.assertEqual(p.steps, restored.steps)
        self.assertEqual(p.occurrence_count, restored.occurrence_count)


class TestHooks(_TempProjectMixin, unittest.TestCase):
    def test_post_tool_use_records(self):
        event = self._post_event("Bash", {"command": "ls"})
        result = handle_post_tool_use(event)
        self.assertEqual(result, {})
        traces = load_all_traces()
        self.assertEqual(len(traces), 1)
    def test_stop_no_patterns_yet(self):
        result = handle_stop({"cwd": str(self.project)})
        self.assertEqual(result, {})
    def test_stop_with_patterns(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [("Read", {"file_path": "x.py"}), ("Edit", {"file_path": "x.py"}), ("Bash", {"command": "test"})])
        result = handle_stop({"cwd": str(self.project)})
        self.assertEqual(result, {})
        patterns = load_patterns()
        self.assertGreater(len(patterns), 0)
    def test_stop_ignores_refire(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [("Read", {"file_path": "x.py"}), ("Edit", {"file_path": "x.py"}), ("Bash", {"command": "test"})])
        result = handle_stop({"cwd": str(self.project), "stop_hook_active": True})
        self.assertEqual(result, {})
    def test_session_start_no_patterns(self):
        result = handle_session_start({"cwd": str(self.project)})
        self.assertEqual(result, {})
    def test_session_start_with_patterns(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [("Read", {"file_path": "x.py"}), ("Edit", {"file_path": "x.py"}), ("Bash", {"command": "test"})])
        detect_patterns()
        patterns = detect_patterns()
        save_patterns(patterns)
        result = handle_session_start({"cwd": str(self.project)})
        self.assertIn("systemMessage", result)
        self.assertIn("pattern", result["systemMessage"].lower())
    def test_session_start_compact_reinjection(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [("Read", {"file_path": "x.py"}), ("Edit", {"file_path": "x.py"}), ("Bash", {"command": "test"})])
        patterns = detect_patterns()
        save_patterns(patterns)
        result = handle_session_start({"cwd": str(self.project), "source": "compact"})
        self.assertIn("systemMessage", result)
        self.assertIn("Re-injecting", result["systemMessage"])
    def test_user_prompt_submit(self):
        event = {"session_id": "s1", "prompt": "fix the tests", "cwd": str(self.project)}
        result = handle_user_prompt_submit(event)
        self.assertEqual(result, {})
        prompts_dir = self.project / ".zoku" / "prompts"
        files = list(prompts_dir.glob("*.jsonl"))
        self.assertEqual(len(files), 1)


class TestInstaller(unittest.TestCase):
    def test_install_creates_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install(tmpdir)
            settings = Path(tmpdir) / ".claude" / "settings.json"
            self.assertTrue(settings.is_file())
            data = json.loads(settings.read_text())
            self.assertIn("PostToolUse", data["hooks"])
            self.assertIn("Stop", data["hooks"])
            self.assertIn("SessionStart", data["hooks"])
            self.assertIn("UserPromptSubmit", data["hooks"])
    def test_install_creates_zoku_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install(tmpdir)
            self.assertTrue((Path(tmpdir) / ".zoku" / "traces").is_dir())
    def test_install_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({"my_key": 42}))
            install(tmpdir)
            data = json.loads(settings_path.read_text())
            self.assertEqual(data["my_key"], 42)
            self.assertIn("hooks", data)
    def test_install_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install(tmpdir)
            install(tmpdir)
            data = json.loads((Path(tmpdir) / ".claude" / "settings.json").read_text())
            self.assertEqual(len(data["hooks"]["PostToolUse"]), 1)
    def test_uninstall_cleans(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install(tmpdir)
            uninstall(tmpdir)
            data = json.loads((Path(tmpdir) / ".claude" / "settings.json").read_text())
            self.assertNotIn("hooks", data)
    def test_uninstall_preserves_other_hooks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / ".claude" / "settings.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "my-hook.sh"}]}]}}))
            install(tmpdir)
            uninstall(tmpdir)
            data = json.loads(settings_path.read_text())
            self.assertIn("hooks", data)
            self.assertEqual(len(data["hooks"]["PostToolUse"]), 1)
    def test_is_zoku_entry(self):
        self.assertTrue(_is_zoku_entry({"hooks": [{"command": "python3 -m zoku.hooks stop"}]}))
        self.assertFalse(_is_zoku_entry({"hooks": [{"command": "other-hook.sh"}]}))
    def test_is_zoku_entry_legacy_deja(self):
        self.assertTrue(_is_zoku_entry({"hooks": [{"command": "python3 -m deja.hooks stop"}]}))


class TestCLI(_TempProjectMixin, unittest.TestCase):
    def test_install_command(self):
        ret = main(["install", "-p", str(self.project)])
        self.assertEqual(ret, 0)
    def test_status_command(self):
        ret = main(["status", "-p", str(self.project)])
        self.assertEqual(ret, 0)
    def test_traces_empty(self):
        ret = main(["traces", "-p", str(self.project)])
        self.assertEqual(ret, 0)
    def test_patterns_empty(self):
        ret = main(["patterns", "-p", str(self.project)])
        self.assertEqual(ret, 0)
    def test_analyse_command(self):
        self._record_session("s1", [("Read", {"file_path": "a.py"}), ("Edit", {"file_path": "a.py"}), ("Bash", {"command": "test"})])
        self._record_session("s2", [("Read", {"file_path": "b.py"}), ("Edit", {"file_path": "b.py"}), ("Bash", {"command": "test"})])
        ret = main(["analyse", "-p", str(self.project)])
        self.assertEqual(ret, 0)
    def test_clear_command(self):
        self._record_session("s1", [("Bash", {"command": "ls"})])
        ret = main(["clear", "-p", str(self.project)])
        self.assertEqual(ret, 0)
        traces = load_all_traces()
        self.assertEqual(len(traces), 0)
    def test_setup_command(self):
        ret = main(["setup"])
        self.assertEqual(ret, 0)
        global_settings = Path.home() / ".claude" / "settings.json"
        if global_settings.is_file():
            data = json.loads(global_settings.read_text())
            self.assertIn("hooks", data)
    def test_no_command_shows_help(self):
        ret = main([])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
