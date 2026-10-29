import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "job_guard.py"
SPEC = importlib.util.spec_from_file_location("job_guard", SCRIPT)
jg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jg)


class JobGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "job.json"

    def command(self, source, seconds=3):
        return [sys.executable, str(SCRIPT), "--cwd", str(self.root), "--max-seconds", str(seconds),
                "--gpu-count", "0", "--report", str(self.report), "--", sys.executable, "-c", source]

    def read_report(self):
        return json.loads(self.report.read_text())

    def test_gpu_allocation_restricts_time_without_launching_gpu_work(self):
        self.assertEqual(jg.grant_seconds(3600, 2, 0.5), 900)
        self.assertEqual(jg.grant_seconds(300, 2, 0.5), 300)
        for args in ((1, 1, None), (1, -1, None), (1, 0, 2), (1, 1, 0), (float("nan"), 0, None)):
            with self.subTest(args=args), self.assertRaises((ValueError, jg.argparse.ArgumentTypeError)):
                jg.grant_seconds(*args)

    def test_success_and_existing_report_does_not_relaunch(self):
        command = self.command("from pathlib import Path; Path('done').write_text('done')")
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_report()["status"], "completed")
        self.assertTrue(self.read_report()["process_group_gone"])
        (self.root / "done").unlink()
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root / "done").exists())

    def test_failed_command_is_not_success(self):
        result = subprocess.run(self.command("raise SystemExit(7)"), capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.read_report()["status"], "failed")

    def test_budget_expiry_kills_uncooperative_job(self):
        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        result = subprocess.run(self.command(code, 0.5), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(self.read_report()["status"], "budget_exhausted")
        self.assertTrue(self.read_report()["process_group_gone"])
        self.assertLess(self.read_report()["elapsed_seconds"], 2)

    def test_interrupt_is_delivered_and_own_child_group_is_cleaned(self):
        code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
        process = subprocess.Popen(self.command(code, 20), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                if self.read_report().get("status") == "running":
                    break
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(0.02)
        else:
            self.fail("guard did not start")
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 143, stderr)
        self.assertEqual(self.read_report()["status"], "interrupted")
        self.assertTrue(self.read_report()["process_group_gone"])

    def test_detached_child_in_own_group_is_not_reported_as_completion(self):
        code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])"
        result = subprocess.run(self.command(code), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.read_report()["status"], "leftover_children")
        self.assertTrue(self.read_report()["process_group_gone"])

    def test_launch_failure_recorded(self):
        result = jg.run_job([str(self.root / "no-such-command")], self.root, 1, 0, None, self.report)
        self.assertEqual(result, 2)
        self.assertEqual(self.read_report()["status"], "launch_failed")

    def test_timeout_does_not_stop_unrelated_process_group(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
        try:
            result = subprocess.run(self.command("import time; time.sleep(60)", 0.4),
                                    capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 124)
            self.assertIsNone(other.poll())
        finally:
            other.terminate()
            other.wait(timeout=3)
