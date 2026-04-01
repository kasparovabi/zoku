"""Comprehensive tests for Phantom Agent."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from phantom.recorder import (
    Action, SessionTrace, summarise_input, record_action,
    load_all_traces, _phantom_dir, _traces_dir,
)
from phantom.detector import (
    detect_patterns, save_patterns, load_patterns,
    WorkflowPattern, _extract_subsequences, _is_contiguous_subset,
)
from phantom.hooks import handle_post_tool_use, handle_stop, handle_session_start
from phantom.installer import install, uninstall, _is_phantom_entry
from phantom.cli import main


class _TempProjectMixin:
    """Create a temp dir simulating a project."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name)
        self._old_env = os.environ.get("PHANTOM_DATA_DIR")
        os.environ["PHANTOM_DATA_DIR"] = str(self.project / ".phantom")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("PHANTOM_DATA_DIR", None)
        else:
            os.environ["PHANTOM_DATA_DIR"] = self._old_env
        self._tmpdir.cleanup()

    def _post_event(self, tool: str, inp: dict, session: str = "s1") -> dict:
        return {
            "tool_name": tool,
            "tool_input": inp,
            "session_id": session,
            "cwd": str(self.project),
        }

    def _record_session(self, session_id: str, steps: list[tuple[str, dict]]):
        for tool, inp in steps:
            record_action(self._post_event(tool, inp, session_id))


# ===================================================================
# Action & SessionTrace
# ===================================================================

class TestAction(unittest.TestCase):

    def test_action_roundtrip(self):
        a = Action("Bash", "ls -la", "2026-01-01T00:00:00Z", "s1", True)
        d = a.to_dict()
        b = Action.from_dict(d)
        self.assertEqual(a, b)

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


# ===================================================================
# Input summarisation
# ===================================================================

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


# ===================================================================
# Recording
# ===================================================================

class TestRecording(_TempProjectMixin, unittest.TestCase):

    def test_record_creates_file(self):
        record_action(self._post_event("Bash", {"command": "ls"}))
        traces = load_all_traces()
        self.assertEqual(len(traces), 1)
        self.assertEqual(len(traces[0].actions), 1)

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


# ===================================================================
# Subsequence extraction
# ===================================================================

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


# ===================================================================
# Pattern detection
# ===================================================================

class TestDetection(_TempProjectMixin, unittest.TestCase):

    def _standard_sessions(self):
        """Create 3 sessions with overlapping patterns."""
        self._record_session("s1", [
            ("Grep", {"pattern": "bug"}),
            ("Read", {"file_path": "a.py"}),
            ("Edit", {"file_path": "a.py"}),
            ("Bash", {"command": "pytest"}),
            ("Bash", {"command": "git commit"}),
        ])
        self._record_session("s2", [
            ("Grep", {"pattern": "error"}),
            ("Read", {"file_path": "b.py"}),
            ("Edit", {"file_path": "b.py"}),
            ("Bash", {"command": "pytest"}),
            ("Bash", {"command": "git commit"}),
        ])
        self._record_session("s3", [
            ("Read", {"file_path": "c.py"}),
            ("Edit", {"file_path": "c.py"}),
            ("Bash", {"command": "pytest"}),
            ("Bash", {"command": "git commit"}),
        ])

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
        self.assertGreater(len(p.steps), 0)

    def test_most_frequent_first(self):
        self._standard_sessions()
        patterns = detect_patterns()
        if len(patterns) > 1:
            self.assertGreaterEqual(patterns[0].occurrence_count, patterns[1].occurrence_count)

    def test_no_patterns_from_one_session(self):
        self._record_session("s1", [
            ("Bash", {"command": "ls"}),
            ("Read", {"file_path": "a.py"}),
            ("Edit", {"file_path": "a.py"}),
        ])
        patterns = detect_patterns()
        self.assertEqual(len(patterns), 0)

    def test_short_sessions_no_patterns(self):
        self._record_session("s1", [("Bash", {"command": "ls"})])
        self._record_session("s2", [("Bash", {"command": "pwd"})])
        patterns = detect_patterns()
        self.assertEqual(len(patterns), 0)

    def test_identical_sessions_detect(self):
        for sid in ("s1", "s2", "s3"):
            self._record_session(sid, [
                ("Read", {"file_path": "x.py"}),
                ("Edit", {"file_path": "x.py"}),
                ("Bash", {"command": "test"}),
            ])
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
        p = WorkflowPattern(
            steps=("Grep", "Read", "Edit", "Bash", "Bash"),
            occurrence_count=2,
            session_ids=("s1", "s2"),
            example_inputs=(),
        )
        self.assertEqual(p.name, "Grep -> Read -> Edit -> Bash")

    def test_pattern_roundtrip(self):
        p = WorkflowPattern(
            steps=("Read", "Edit"),
            occurrence_count=3,
            session_ids=("s1", "s2", "s3"),
            example_inputs=("a.py", "edit:a.py"),
        )
        restored = WorkflowPattern.from_dict(p.to_dict())
        self.assertEqual(p.steps, restored.steps)
        self.assertEqual(p.occurrence_count, restored.occurrence_count)


# ===================================================================
# Hook handlers
# ===================================================================

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
            self._record_session(sid, [
                ("Read", {"file_path": "x.py"}),
                ("Edit", {"file_path": "x.py"}),
                ("Bash", {"command": "test"}),
            ])
        result = handle_stop({"cwd": str(self.project)})
        self.assertIn("additionalContext", result)
        self.assertIn("Phantom Agent", result["additionalContext"])

    def test_stop_ignores_refire(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [
                ("Read", {"file_path": "x.py"}),
                ("Edit", {"file_path": "x.py"}),
                ("Bash", {"command": "test"}),
            ])
        result = handle_stop({"cwd": str(self.project), "stop_hook_active": True})
        self.assertEqual(result, {})

    def test_session_start_no_patterns(self):
        result = handle_session_start({"cwd": str(self.project)})
        self.assertEqual(result, {})

    def test_session_start_with_patterns(self):
        for sid in ("s1", "s2"):
            self._record_session(sid, [
                ("Read", {"file_path": "x.py"}),
                ("Edit", {"file_path": "x.py"}),
                ("Bash", {"command": "test"}),
            ])
        detect_patterns()
        patterns = detect_patterns()
        save_patterns(patterns)
        result = handle_session_start({"cwd": str(self.project)})
        self.assertIn("additionalContext", result)
        self.assertIn("pattern", result["additionalContext"].lower())


# ===================================================================
# Installer
# ===================================================================

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

    def test_install_creates_phantom_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            install(tmpdir)
            self.assertTrue((Path(tmpdir) / ".phantom" / "traces").is_dir())

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
            settings_path.write_text(json.dumps({
                "hooks": {"PostToolUse": [
                    {"hooks": [{"type": "command", "command": "my-hook.sh"}]}
                ]}
            }))
            install(tmpdir)
            uninstall(tmpdir)
            data = json.loads(settings_path.read_text())
            self.assertIn("hooks", data)
            self.assertEqual(len(data["hooks"]["PostToolUse"]), 1)

    def test_is_phantom_entry(self):
        self.assertTrue(_is_phantom_entry(
            {"hooks": [{"command": "python3 -m phantom.hooks stop"}]}
        ))
        self.assertFalse(_is_phantom_entry(
            {"hooks": [{"command": "other-hook.sh"}]}
        ))


# ===================================================================
# CLI
# ===================================================================

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
        self._record_session("s1", [
            ("Read", {"file_path": "a.py"}),
            ("Edit", {"file_path": "a.py"}),
            ("Bash", {"command": "test"}),
        ])
        self._record_session("s2", [
            ("Read", {"file_path": "b.py"}),
            ("Edit", {"file_path": "b.py"}),
            ("Bash", {"command": "test"}),
        ])
        ret = main(["analyse", "-p", str(self.project)])
        self.assertEqual(ret, 0)

    def test_clear_command(self):
        self._record_session("s1", [("Bash", {"command": "ls"})])
        ret = main(["clear", "-p", str(self.project)])
        self.assertEqual(ret, 0)
        traces = load_all_traces()
        self.assertEqual(len(traces), 0)

    def test_no_command_shows_help(self):
        ret = main([])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
