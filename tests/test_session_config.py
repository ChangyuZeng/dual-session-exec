import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "session_config.py"
SPEC = importlib.util.spec_from_file_location("session_config", SCRIPT)
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)


class SessionConfigTests(unittest.TestCase):
    def session(self, **kwargs):
        return sc.create_session("run-1", "codex", "用户本轮选择", **kwargs)

    def test_roles_are_independent_and_have_no_fixed_default(self):
        session = self.session(parent_model="provider/planner", parent_thinking="deep",
                               worker_model="other/executor", worker_thinking="budget-1024")
        settings = session["role_model_settings"]
        self.assertEqual(settings["parent"]["requested_thinking"], "deep")
        self.assertEqual(settings["worker"]["requested_thinking"], "budget-1024")
        self.assertIsNone(settings["parent"]["runtime_confirmation"])
        self.assertIsNone(settings["worker"]["runtime_confirmation"])
        for role in self.session()["role_model_settings"].values():
            self.assertIsNone(role["requested_model"])
            self.assertIsNone(role["requested_thinking"])

    def test_change_invalidates_only_selected_role_observation_and_keeps_identity(self):
        session = self.session(parent_model="planner", worker_model="executor")
        session["worker_thread_id"] = "actual-worker"
        for role in session["role_model_settings"].values():
            role["runtime_confirmation"] = {"source": "old turn"}
        result = sc.select(session, "worker", {"requested_thinking": "high"}, "新指令")
        self.assertEqual(result["worker_thread_id"], "actual-worker")
        self.assertEqual(result["role_model_settings"]["parent"], session["role_model_settings"]["parent"])
        self.assertIsNone(result["role_model_settings"]["worker"]["runtime_confirmation"])
        self.assertEqual(result["role_model_settings"]["worker"]["config_revision"], 2)
        self.assertIsNotNone(session["role_model_settings"]["worker"]["runtime_confirmation"])

    def test_inherit_is_omission_not_a_model_or_thinking_value(self):
        session = self.session(worker_model="inherit", worker_thinking="inherit")
        worker = session["role_model_settings"]["worker"]
        self.assertIsNone(worker["requested_model"])
        self.assertIsNone(worker["requested_thinking"])
        changed = sc.select(self.session(worker_model="executor"), "worker",
                            {"requested_model": "inherit"}, "恢复宿主默认")
        self.assertIsNone(changed["role_model_settings"]["worker"]["requested_model"])

    def test_bad_values_and_legacy_migration_are_rejected(self):
        for kwargs in ({"worker_model": ""}, {"worker_thinking": "unsupported"}, {"parent_model": 3}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.session(**kwargs)
        with self.assertRaises(ValueError):
            sc.select({"run_id": "legacy"}, "worker", {"requested_model": "new"}, "更新")
        with self.assertRaises(ValueError):
            sc.select(self.session(), "worker", {}, "更新")

    def test_cli_preserves_literal_text_refuses_overwrite_and_reports_no_runtime_control(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            command = [sys.executable, str(SCRIPT), "init", "--out", str(path), "--run-id", "run-1",
                       "--adapter", "manual", "--source", "literal $(command) `text`",
                       "--worker-model", "provider/model"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["runtime_applied"])
            before = path.read_bytes()
            self.assertEqual(json.loads(before)["role_model_settings"]["worker"]["selection_source"],
                             "literal $(command) `text`")
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(before, path.read_bytes())
            change = subprocess.run([sys.executable, str(SCRIPT), "select", "--session", str(path),
                                     "--role", "parent", "--thinking", "inherit", "--source", "新选择"],
                                    capture_output=True, text=True)
            self.assertEqual(change.returncode, 0, change.stderr)
            data = json.loads(path.read_text())
            self.assertEqual(data["role_model_settings"]["parent"]["config_revision"], 2)
            self.assertEqual(data["role_model_settings"]["worker"]["requested_model"], "provider/model")
