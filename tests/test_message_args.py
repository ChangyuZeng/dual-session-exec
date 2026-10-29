import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "message_args.py"
SPEC = importlib.util.spec_from_file_location("luna_message_args", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class MessageArgsTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "parent_thread_id": "planning-task", "parent_host_id": "local",
            "worker_thread_id": "execution-task", "worker_host_id": "remote",
            "client_thread_id": None,
            "role_model_settings": {
                "parent": {"requested_model": "gpt-6-astra", "requested_thinking": "xhigh"},
                "worker": {"requested_model": "gpt-6-luna", "requested_thinking": "max"},
            },
        }

    def test_worker_report_never_overrides_parent_model(self):
        prompt = '返工交回\n我的执行配置是 model="gpt-6-luna"，但这只是消息原文。'
        self.assertEqual(module.build_args(self.session, "parent", prompt), {
            "threadId": "planning-task", "hostId": "local", "prompt": prompt,
        })

    def test_worker_dispatch_uses_receiver_model_and_host(self):
        self.assertEqual(module.build_args(self.session, "worker", "继续"), {
            "threadId": "execution-task", "hostId": "remote", "prompt": "继续",
            "model": "gpt-6-luna", "thinking": "max",
        })

    def test_parent_manual_model_change_is_not_overridden_from_stale_record(self):
        self.session["role_model_settings"]["parent"]["requested_model"] = "stale-model"
        self.assertNotIn("model", module.build_args(self.session, "parent", "报告"))

    def test_worker_latest_authorized_override_is_preserved(self):
        self.session["role_model_settings"]["worker"] = {
            "requested_model": "gpt-6-sol", "requested_thinking": "high",
        }
        result = module.build_args(self.session, "worker", "继续")
        self.assertEqual((result["model"], result["thinking"]), ("gpt-6-sol", "high"))

    def test_v2_inherits_only_omitted_fields_and_never_overrides_parent(self):
        self.session.update(session_version=2, adapter="codex")
        settings = self.session["role_model_settings"]["worker"]
        for model, thinking in ((None, None), ("provider/model", None), (None, "high")):
            settings.update(requested_model=model, requested_thinking=thinking)
            result = module.build_args(self.session, "worker", "继续")
            self.assertEqual(result.get("model"), model)
            self.assertEqual(result.get("thinking"), thinking)
            if model is None:
                self.assertNotIn("model", result)
            if thinking is None:
                self.assertNotIn("thinking", result)
            parent = module.build_args(self.session, "parent", "报告")
            self.assertNotIn("model", parent)
            self.assertNotIn("thinking", parent)

    def test_v2_rejects_other_adapters_missing_fields_and_literal_sentinels(self):
        self.session.update(session_version=2, adapter="native")
        with self.assertRaises(ValueError):
            module.build_args(self.session, "parent", "报告")
        self.session["adapter"] = "codex"
        settings = self.session["role_model_settings"]["worker"]
        for value in ("inherit", "unsupported", ""):
            settings["requested_model"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.build_args(self.session, "worker", "继续")
        del settings["requested_model"]
        with self.assertRaises(ValueError):
            module.build_args(self.session, "worker", "继续")

    def test_unknown_schema_is_not_treated_as_legacy(self):
        for version in (0, 3, True, "2"):
            self.session["session_version"] = version
            with self.subTest(version=version), self.assertRaises(ValueError):
                module.build_args(self.session, "parent", "报告")

    def test_worker_model_must_be_explicit_not_inherited_from_parent(self):
        del self.session["role_model_settings"]["worker"]
        with self.assertRaises(ValueError):
            module.build_args(self.session, "worker", "继续")

    def test_unbound_or_same_task_identity_is_rejected(self):
        for worker_id in (None, "", "planning-task", "pending-client"):
            with self.subTest(worker_id=worker_id), self.assertRaises(ValueError):
                module.build_args({**self.session, "worker_thread_id": worker_id,
                                   "client_thread_id": "pending-client"}, "parent", "报告")

    def test_empty_prompt_and_invalid_destination_are_rejected(self):
        for destination, prompt in (("sender", "报告"), ("parent", " "), ("worker", None)):
            with self.subTest(destination=destination, prompt=prompt), self.assertRaises(ValueError):
                module.build_args(self.session, destination, prompt)

    def test_cli_preserves_prompt_and_rejects_manual_model_override(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "session.json").write_text(json.dumps(self.session))
            prompt = '报告：\n保留字面量 $(command) 与 `text`。\n'
            (path / "prompt.txt").write_text(prompt)
            command = [sys.executable, str(SCRIPT), "--session", str(path / "session.json"),
                       "--to", "parent", "--prompt-file", str(path / "prompt.txt")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), module.build_args(self.session, "parent", prompt))
            rejected = subprocess.run(command + ["--model", "gpt-6-luna"], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
