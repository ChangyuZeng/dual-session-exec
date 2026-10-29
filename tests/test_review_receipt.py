import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "review_receipt.py"
SPEC = importlib.util.spec_from_file_location("review_receipt", SCRIPT)
rr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rr)


class ReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.code = self.root / "core"
        self.code.mkdir()
        (self.code / "implementation.py").write_text("return 1\n")
        self.evidence = self.root / "tests.txt"
        self.evidence.write_text("required checks passed\n")
        self.review = self.root / "review.md"
        self.review.write_text("主任务已独立验证对应快照。\n")
        self.manifest = {
            "run_id": "run-1", "item_id": "core-1", "criteria": "批准的核心验证全部通过",
            "context": {"command": "test core", "environment": "image-sha256:one", "data": "dataset-sha256:one"},
            "inputs": [str(self.code)], "evidence": [str(self.evidence)],
        }
        self.session = {"run_id": "run-1", "parent_thread_id": "parent", "worker_thread_id": "worker"}
        self.decision = {"run_id": "run-1", "item_id": "core-1", "reviewer_thread_id": "parent",
                         "verdict": "accepted", "required_fixes": [], "report_path": str(self.review)}
        self.snapshot = rr.capture(self.manifest)
        self.receipt = rr.seal(self.snapshot, self.decision, self.session)

    def test_unchanged_acceptance_reused_without_running_checks(self):
        self.assertEqual(rr.check(self.manifest, self.receipt, self.session),
                         {"run_id": "run-1", "item_id": "core-1", "reusable": True, "changed": []})

    def test_content_change_detected_even_if_size_and_mtime_match(self):
        path = self.code / "implementation.py"
        original = path.stat()
        path.write_text("return 2\n")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        result = rr.check(self.manifest, self.receipt, self.session)
        self.assertFalse(result["reusable"])
        self.assertIn(str(path), result["changed"])

    def test_new_and_removed_dependency_invalidate_directory_snapshot(self):
        extra = self.code / "new_dependency.py"
        extra.write_text("new\n")
        self.assertFalse(rr.check(self.manifest, self.receipt, self.session)["reusable"])
        extra.unlink()
        self.assertTrue(rr.check(self.manifest, self.receipt, self.session)["reusable"])
        (self.code / "implementation.py").unlink()
        self.assertFalse(rr.check(self.manifest, self.receipt, self.session)["reusable"])

    def test_environment_criteria_and_evidence_changes_invalidate(self):
        for key in ("environment", "command", "data"):
            manifest = copy.deepcopy(self.manifest)
            manifest["context"][key] = "changed"
            with self.subTest(key=key):
                self.assertFalse(rr.check(manifest, self.receipt, self.session)["reusable"])
        manifest = {**self.manifest, "criteria": "new acceptance requirements"}
        self.assertFalse(rr.check(manifest, self.receipt, self.session)["reusable"])
        self.evidence.write_text("different results\n")
        self.assertFalse(rr.check(self.manifest, self.receipt, self.session)["reusable"])

    def test_unrelated_optional_work_does_not_reopen_core_acceptance(self):
        (self.root / "optional-fp8.txt").write_text("optional experiment incomplete\n")
        self.assertTrue(rr.check(self.manifest, self.receipt, self.session)["reusable"])

    def test_changed_inputs_cannot_be_sealed_after_review(self):
        self.evidence.write_text("changed after snapshot\n")
        with self.assertRaises(ValueError):
            rr.seal(self.snapshot, self.decision, self.session)

    def test_wrong_reviewer_run_item_or_unresolved_required_fixes_rejected(self):
        for patch in ({"reviewer_thread_id": "worker"}, {"run_id": "other"},
                      {"item_id": "other"}, {"verdict": "rework"}, {"required_fixes": ["M1"]}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                rr.seal(self.snapshot, {**self.decision, **patch}, self.session)
        with self.assertRaises(ValueError):
            rr.check(self.manifest, self.receipt, {**self.session, "parent_thread_id": "other"})

    def test_missing_inputs_and_links_fail_closed(self):
        self.evidence.unlink()
        with self.assertRaises(ValueError):
            rr.check(self.manifest, self.receipt, self.session)
        linked = self.root / "linked"
        linked.symlink_to(self.code, target_is_directory=True)
        with self.assertRaises(ValueError):
            rr.fingerprint([str(linked)])

    def test_report_change_invalidates_and_existing_receipt_is_immutable(self):
        self.review.write_text("withdraw acceptance\n")
        self.assertFalse(rr.check(self.manifest, self.receipt, self.session)["reusable"])
        output = self.root / "receipt.json"
        rr.write_new(output, self.receipt)
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            rr.write_new(output, {})
        self.assertEqual(output.read_bytes(), original)

    def test_cli_snapshot_seal_check_and_invalidated_exit_codes(self):
        for name, data in (("manifest", self.manifest), ("decision", self.decision), ("session", self.session)):
            (self.root / f"{name}.json").write_text(json.dumps(data))

        def call(action, **kwargs):
            command = [sys.executable, str(SCRIPT), action]
            for key, value in kwargs.items():
                command.extend([f"--{key}", str(self.root / value)])
            return subprocess.run(command, text=True, capture_output=True)

        self.assertEqual(call("snapshot", manifest="manifest.json", out="snapshot.json").returncode, 0)
        self.assertEqual(call("seal", snapshot="snapshot.json", decision="decision.json",
                              session="session.json", out="accepted.json").returncode, 0)
        self.assertEqual(call("check", manifest="manifest.json", receipt="accepted.json", session="session.json").returncode, 0)
        self.evidence.write_text("changed")
        self.assertEqual(call("check", manifest="manifest.json", receipt="accepted.json", session="session.json").returncode, 1)
        self.evidence.unlink()
        self.assertEqual(call("check", manifest="manifest.json", receipt="accepted.json", session="session.json").returncode, 2)
