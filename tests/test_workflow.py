import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "supervision.py"
SPEC = importlib.util.spec_from_file_location("workflow_supervision", SCRIPT)
sv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sv)
START = dt.datetime(2026, 9, 12, tzinfo=dt.timezone.utc)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.initial = sv.init_run(self.run, worker_target="luna-session:test", objective="测试工作包",
                                   parent_thread_id="parent", mode="standard", now=START)

    def state(self):
        return sv.load_state(self.run / "state.json")

    def item(self, key, status="done", **kwargs):
        item = copy.deepcopy(self.state()["workflow"]["todos"][key])
        item.update(status=status, evidence=["实际测试回执"] if status == "done" else [],
                    next_action="" if status == "done" else "继续对应工作", **kwargs)
        return item

    def parent(self, patch, minutes=0):
        return sv.update_parent(self.run, patch, now=START + dt.timedelta(minutes=minutes))

    def worker(self, patch):
        return sv.update_worker(self.run, patch, now=START)

    def prepare(self):
        self.parent({"worker_thread_id": "worker", "todos": {"plan": self.item("plan")}})

    def recovery(self, kind="parent_wait", minutes=240):
        return {"kind": kind, "reference": "worker" if kind == "parent_wait" else "timer-1",
                "check_at": sv.iso(START + dt.timedelta(minutes=minutes)), "evidence": ["实际工具回执"]}

    def resolution(self, mode="continue", issue_id=None):
        return {"mode": mode, "issue_id": issue_id, "evidence": ["主任务诊断或验收回执"]}

    def complete_execution(self):
        self.worker({"state": "ready_for_review", "writes_paused": True,
                     "todos": {"execute": self.item("execute")}})

    def test_default_cli_is_standard_with_pending_parent_work_and_no_timer(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "init", "--run-dir", str(Path(self.temp.name) / "cli"),
                                 "--worker-target", "luna-session:cli", "--objective", "目标"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["workflow"]["mode"], "standard")
        self.assertIsNone(state["parent"]["next_check_at"])
        result = sv.check_run(self.run, now=START)
        self.assertEqual(result["action"], "continue_parent")
        self.assertEqual(result["ready_parent_todos"], ["plan"])

    def test_goal_mode_is_explicit_and_cannot_silently_change_existing_run(self):
        other = Path(self.temp.name) / "goal"
        state = sv.init_run(other, worker_target="luna-session:goal", objective="目标", mode="goal", now=START)
        self.assertEqual(state["workflow"]["mode"], "goal")
        with self.assertRaises(sv.StateError):
            sv.init_run(other, worker_target="luna-session:goal", objective="目标", mode="standard", now=START)

    def test_compact_check_retains_review_job_and_evidence_without_changing_state(self):
        self.prepare()
        self.parent({"recovery": self.recovery()})
        self.worker({"state": "ready_for_review", "writes_paused": True,
                     "summary": "完成正式运行，待独立验收", "evidence": ["结果.json", "指标检查.log"],
                     "jobs": [{"job_id": "host:experiment-1", "kind": "local", "pid": None,
                               "write_scope": ["results"], "status": "completed"}],
                     "todos": {"execute": self.item("execute")}})
        before = (self.run / "state.json").read_bytes()
        full = sv.check_run(self.run, force=True, now=START)
        compact = sv.check_run(self.run, force=True, compact=True, now=START)
        for key in ("run_id", "action", "reason", "worker_state", "parent_state", "writes_paused",
                    "jobs", "evidence", "pending_todos", "ready_parent_todos", "recovery", "next_check_at"):
            self.assertEqual(compact[key], full[key])
        self.assertEqual(compact["action"], "review")
        self.assertEqual(Path(compact["state_path"]).read_bytes(), before)
        self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_compact_check_keeps_pending_decision_but_omits_old_history(self):
        self.prepare()
        for number in range(5):
            request_id = f"stage:{number}"
            self.complete_execution()
            self.parent({"resume_worker": True, "request_id": request_id, "decision": "进入下一获准阶段",
                         "resolution": self.resolution()})
            self.worker({"state": "running", "last_applied_request_id": request_id, "writes_paused": False})
        self.complete_execution()
        self.parent({"resume_worker": True, "request_id": "stage:final", "decision": "收集已运行结果",
                     "resolution": self.resolution()})
        full = sv.check_run(self.run, now=START)
        compact = sv.check_run(self.run, compact=True, now=START)
        self.assertEqual(compact["action"], "await_worker_resume")
        self.assertEqual(compact["pending_resolution"], full["resolution_history"][-1])
        self.assertEqual((compact["request_id"], compact["decision"]), ("stage:final", "收集已运行结果"))
        self.assertNotIn("resolution_history", compact)
        self.assertEqual(len(self.state()["workflow"]["resolution_history"]), 6)

    def test_compact_cli_and_legacy_check_remain_readonly(self):
        before = (self.run / "state.json").read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPT), "check", "--run-dir", str(self.run),
                                 "--compact", "--force"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        compact = json.loads(result.stdout)
        self.assertEqual(compact["action"], "continue_parent")
        self.assertEqual(compact["pending_todos"], ["plan", "execute", "review", "close"])
        self.assertEqual((self.run / "state.json").read_bytes(), before)
        legacy = Path(self.temp.name) / "legacy"
        sv.init_run(legacy, worker_target="legacy", objective="保留旧运行", now=START)
        original = (legacy / "state.json").read_bytes()
        self.assertEqual(sv.check_run(legacy, compact=True, now=START)["action"],
                         sv.check_run(legacy, now=START)["action"])
        self.assertEqual((legacy / "state.json").read_bytes(), original)

    def test_compact_check_preserves_blocker_and_single_retry_takeover(self):
        self.prepare()
        blocker = {"kind": "repair", "issue_id": "experiment:loader", "request_id": "loader:r1",
                   "reason": "加载失败", "first_seen_at": sv.iso(START), "attempts": [],
                   "requested_help": "请主任务定位"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": blocker,
                     "evidence": ["加载错误.log"]})
        compact = sv.check_run(self.run, compact=True, now=START)
        self.assertEqual((compact["action"], compact["blocker"], compact["evidence"]),
                         ("help", blocker, ["加载错误.log"]))
        self.parent({"resume_worker": True, "request_id": "loader:r1", "decision": "修正已定位的加载参数",
                     "resolution": self.resolution("worker_retry", "experiment:loader")})
        self.worker({"state": "running", "writes_paused": False, "last_applied_request_id": "loader:r1"})
        blocker = {**blocker, "request_id": "loader:r2"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": blocker})
        compact = sv.check_run(self.run, compact=True, now=START)
        self.assertEqual(compact["action"], "takeover")
        self.assertEqual(compact["blocker"], blocker)
        self.assertEqual(compact["action"], sv.check_run(self.run, now=START)["action"])
        self.assertEqual(len(self.state()["workflow"]["resolution_history"]), 1)

    def test_experiment_steps_require_dependencies_and_resume_without_reopening_done_steps(self):
        self.prepare()
        steps = ("prepare", "smoke", "run", "analyze")
        patch = {}
        dependency = "plan"
        for step in steps:
            key = f"experiment:{step}"
            patch[key] = {"title": step, "owner": "worker", "status": "todo", "depends_on": [dependency],
                          "evidence": [], "next_action": f"执行 {step}", "waiting_for": None}
            dependency = key
        patch["execute"] = self.item("execute", status="todo", depends_on=[dependency])
        self.parent({"todos": patch})
        with self.assertRaises(sv.StateError):
            self.worker({"todos": {"experiment:run": self.item("experiment:run")}})
        for step in steps:
            key = f"experiment:{step}"
            completed = self.item(key)
            completed["evidence"] = [f"{step}:input-config-output-checked.json"]
            self.worker({"phase": key, "state": "running", "summary": f"完成 {step}",
                         "todos": {key: completed}})
            before = self.state()["workflow"]["todos"]
            sv.check_run(self.run, compact=True, force=True, now=START)
            self.assertEqual(self.state()["workflow"]["todos"], before)
        self.complete_execution()
        self.assertEqual(sv.check_run(self.run, compact=True, now=START)["action"], "review")
        self.assertEqual(sv.check_run(self.run, compact=True, now=START)["pending_todos"], ["review", "close"])

    def test_no_recovery_reports_missing_liveness_not_completion(self):
        self.prepare()
        result = sv.check_run(self.run, now=START)
        self.assertEqual(result["action"], "arrange_recovery")
        self.assertIn("review", result["pending_todos"])

    def test_long_job_has_no_thirty_minute_check_and_observation_does_not_move_deadline(self):
        self.prepare()
        self.parent({"recovery": self.recovery()})
        self.worker({"state": "waiting_external", "expected_until": self.recovery()["check_at"],
                     "summary": "训练正常", "evidence": ["作业回执"]})
        for minutes in (30, 60, 120, 239):
            result = sv.check_run(self.run, now=START + dt.timedelta(minutes=minutes))
            self.assertFalse(result["due"])
            self.assertEqual(result["action"], "not_due")
        self.parent({"check_completed": True}, minutes=60)
        self.assertEqual(self.state()["parent"]["next_check_at"], self.recovery()["check_at"])
        result = sv.check_run(self.run, now=START + dt.timedelta(minutes=240))
        self.assertTrue(result["due"])
        self.assertEqual(result["action"], "investigate")

    def test_review_event_ignores_later_fallback_deadline(self):
        self.prepare()
        self.parent({"recovery": self.recovery()})
        self.complete_execution()
        result = sv.check_run(self.run, now=START + dt.timedelta(minutes=1))
        self.assertEqual(result["action"], "review")
        self.assertFalse(result["due"])

    def test_repair_escalation_precedes_routine_parent_todo(self):
        self.prepare()
        extra = self.item("plan", "todo")
        self.parent({"todos": {"extra-parent-work": extra}})
        self.worker({"state": "running", "blocker": {
            "kind": "repair", "issue_id": "failure", "request_id": "failure:r1", "reason": "两次修复失败",
            "first_seen_at": sv.iso(START), "requested_help": "请诊断",
            "attempts": [{"method": "repair-one", "result": "failed"},
                         {"method": "repair-two", "result": "failed"}]}})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "help")

    def test_yield_requires_real_idle_recovery_and_no_actionable_parent_todo(self):
        self.prepare()
        for patch in ({"yield_parent": True}, {"recovery": self.recovery(), "yield_parent": True}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.parent(patch)
        self.parent({"automation_id": "timer-1", "recovery": self.recovery("heartbeat"), "yield_parent": True})
        self.complete_execution()
        with self.assertRaises(sv.StateError):
            self.parent({"yield_parent": True})
        with self.assertRaises(sv.StateError):
            self.parent({"recovery": self.recovery("heartbeat", minutes=0), "yield_parent": True})

    def test_unverified_events_and_wrong_heartbeat_are_rejected(self):
        self.prepare()
        for recovery in (self.recovery("silent_event"), self.recovery("heartbeat"),
                         {**self.recovery(), "evidence": []}, {**self.recovery(), "reference": "different-worker"}):
            with self.subTest(recovery=recovery), self.assertRaises(sv.StateError):
                self.parent({"recovery": recovery})

    def test_yield_rejects_handoffs_even_when_worker_todos_are_stale(self):
        self.prepare()
        self.parent({"automation_id": "timer-1", "recovery": self.recovery("heartbeat")})
        blocker = {"kind": "decision", "issue_id": "cost-gate", "request_id": "cost-gate:r1",
                   "reason": "首批已完成，待成本门裁定", "first_seen_at": sv.iso(START),
                   "attempts": [], "requested_help": "请裁定下一阶段"}
        for worker_state, action in (("needs_parent", "help"), ("ready_for_review", "review")):
            with self.subTest(worker_state=worker_state):
                if worker_state == "ready_for_review":
                    self.parent({"resume_worker": True, "request_id": "cost-gate:r1", "decision": "提交验收",
                                 "resolution": self.resolution()})
                    self.worker({"state": "running", "blocker": None,
                                 "last_applied_request_id": "cost-gate:r1"})
                self.worker({"state": worker_state, "writes_paused": True,
                             "blocker": blocker if worker_state == "needs_parent" else None})
                result = sv.check_run(self.run, now=START)
                self.assertEqual(result["action"], action)
                self.assertFalse(result["due"])
                self.assertEqual(result["ready_parent_todos"], [])
                before = (self.run / "state.json").read_bytes()
                with self.assertRaises(sv.StateError):
                    self.parent({"yield_parent": True})
                self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_yield_rejects_active_parent_intervention_and_repair_escalation(self):
        self.prepare()
        self.parent({"automation_id": "timer-1", "recovery": self.recovery("heartbeat")})
        self.parent({"state": "helping"})
        with self.assertRaises(sv.StateError):
            self.parent({"yield_parent": True})
        self.parent({"state": "watching"})
        self.worker({"state": "running", "blocker": {
            "kind": "repair", "issue_id": "failure", "request_id": "failure:r1", "reason": "两次修复失败",
            "first_seen_at": sv.iso(START), "requested_help": "请诊断",
            "attempts": [{"method": "repair-one", "result": "failed"},
                         {"method": "repair-two", "result": "failed"}]}})
        with self.assertRaises(sv.StateError):
            self.parent({"yield_parent": True})

    def test_yield_allows_consumed_guidance_with_real_recovery(self):
        self.prepare()
        self.parent({"automation_id": "timer-1", "recovery": self.recovery("heartbeat")})
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": {
            "kind": "decision", "issue_id": "cost-gate", "request_id": "cost-gate:r1", "reason": "待裁定",
            "first_seen_at": sv.iso(START), "attempts": [], "requested_help": "请裁定"}})
        self.parent({"resume_worker": True, "request_id": "cost-gate:r1", "decision": "继续获准阶段",
                     "resolution": self.resolution()})
        self.worker({"state": "running", "writes_paused": False, "blocker": None,
                     "last_applied_request_id": "cost-gate:r1"})
        self.parent({"yield_parent": True})
        self.assertEqual(self.state()["worker"]["state"], "running")

    def test_same_repair_gets_one_worker_retry_then_requires_parent_takeover(self):
        self.prepare()
        first = {"kind": "repair", "issue_id": "compile", "request_id": "compile:r1",
                 "reason": "编译仍失败", "first_seen_at": sv.iso(START), "attempts": [],
                 "requested_help": "请诊断"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": first})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "help")
        self.parent({"resume_worker": True, "request_id": "compile:r1", "decision": "按已定位根因修复一次",
                     "resolution": self.resolution("worker_retry", "compile")})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "await_worker_resume")
        self.worker({"state": "running", "writes_paused": False,
                     "last_applied_request_id": "compile:r1"})
        second = {**first, "request_id": "compile:r2",
                  "attempts": [{"method": "按主任务定位修改", "result": "failed"}]}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": second})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "takeover")
        before = (self.run / "state.json").read_bytes()
        with self.assertRaises(sv.StateError):
            self.parent({"resume_worker": True, "request_id": "compile:r2", "decision": "再试一次",
                         "resolution": self.resolution("worker_retry", "compile")})
        self.assertEqual((self.run / "state.json").read_bytes(), before)

        self.parent({"state": "helping", "request_id": "compile:r2", "decision": "主任务接管修改"})
        self.parent({"resume_worker": True, "request_id": "compile:r2", "decision": "主任务已修复，仅验证并继续",
                     "resolution": self.resolution("parent_takeover", "compile")})
        self.worker({"state": "running", "writes_paused": False, "blocker": None,
                     "last_applied_request_id": "compile:r2"})
        history = self.state()["workflow"]["resolution_history"]
        self.assertEqual([item["mode"] for item in history], ["worker_retry", "parent_takeover"])
        self.assertIsNone(self.state()["worker"]["repair_round"])

    def test_parent_takeover_requires_helping_and_same_issue_stays_with_parent(self):
        self.prepare()
        blocker = {"kind": "repair", "issue_id": "architecture", "request_id": "architecture:r1",
                   "reason": "跨模块设计错误", "first_seen_at": sv.iso(START), "attempts": [],
                   "requested_help": "请主任务接管"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": blocker})
        with self.assertRaises(sv.StateError):
            self.parent({"resume_worker": True, "request_id": "architecture:r1", "decision": "已修复",
                         "resolution": self.resolution("parent_takeover", "architecture")})
        self.parent({"state": "helping", "request_id": "architecture:r1", "decision": "核实暂停后接管"})
        self.parent({"resume_worker": True, "request_id": "architecture:r1", "decision": "已完成修改，仅做验证",
                     "resolution": self.resolution("parent_takeover", "architecture")})
        self.worker({"state": "running", "writes_paused": False, "blocker": None,
                     "last_applied_request_id": "architecture:r1"})
        repeated = {**blocker, "request_id": "architecture:r2", "reason": "主任务修复后的验证仍失败"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": repeated})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "takeover")

    def test_parent_takeover_requires_worker_pause_and_resolution_schema(self):
        self.prepare()
        blocker = {"kind": "repair", "issue_id": "runtime", "request_id": "runtime:r1",
                   "reason": "运行时故障", "first_seen_at": sv.iso(START), "attempts": [],
                   "requested_help": "请主任务接管"}
        self.worker({"state": "needs_parent", "writes_paused": False, "blocker": blocker})
        self.parent({"state": "helping", "request_id": "runtime:r1", "decision": "准备接管"})
        invalid = [
            {"resume_worker": True, "request_id": "runtime:r1", "decision": "缺少暂停证据",
             "resolution": self.resolution("parent_takeover", "runtime")},
            {"resume_worker": True, "request_id": "runtime:r1", "decision": "错误路由",
             "resolution": self.resolution("continue")},
            {"resume_worker": True, "request_id": "runtime:r1", "decision": "缺少证据",
             "resolution": {"mode": "worker_retry", "issue_id": "runtime", "evidence": []}},
        ]
        for patch in invalid:
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.parent(patch)
        self.assertEqual(self.state()["workflow"]["resolution_history"], [])

    def test_repeated_review_rework_cannot_be_sent_back_to_worker(self):
        self.prepare()
        self.complete_execution()
        self.parent({"resume_worker": True, "request_id": "review:r1", "decision": "修复 M1",
                     "resolution": self.resolution("worker_retry", "review:core")})
        self.worker({"state": "running", "writes_paused": False,
                     "last_applied_request_id": "review:r1"})
        self.worker({"state": "ready_for_review", "writes_paused": True})
        with self.assertRaises(sv.StateError):
            self.parent({"resume_worker": True, "request_id": "review:r2", "decision": "再次修复 M1",
                         "resolution": self.resolution("worker_retry", "review:core")})
        self.parent({"state": "helping", "request_id": "review:r2", "decision": "主任务接管 M1"})
        self.parent({"resume_worker": True, "request_id": "review:r2", "decision": "主任务已修复，Luna 只验证",
                     "resolution": self.resolution("parent_takeover", "review:core")})

    def test_existing_workflow_without_resolution_history_keeps_old_semantics(self):
        state = self.state()
        del state["workflow"]["resolution_history"]
        sv.atomic_write(self.run / "state.json", state)
        blocker = {"issue_id": "legacy", "request_id": "legacy:r1", "reason": "旧记录问题",
                   "first_seen_at": sv.iso(START), "attempts": [], "requested_help": "请指导"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": blocker})
        self.parent({"resume_worker": True, "request_id": "legacy:r1", "decision": "沿用旧恢复语义"})
        self.worker({"state": "running", "writes_paused": False,
                     "last_applied_request_id": "legacy:r1"})
        self.assertNotIn("resolution_history", self.state()["workflow"])

    def test_user_pause_does_not_autoresume_when_forced(self):
        self.parent({"state": "awaiting_user", "recovery": {"kind": "user", "reference": "用户暂停指令",
                    "check_at": None, "evidence": ["实际用户消息"]}, "yield_parent": True})
        self.assertEqual(sv.check_run(self.run, now=START, force=True)["action"], "await_user")

    def test_worker_cannot_mark_parent_review_done_or_add_its_own_tasks(self):
        self.prepare()
        for patch in ({"plan": self.item("plan")}, {"new": self.item("execute", "todo")}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.worker({"todos": patch})

    def test_dependencies_and_done_evidence_are_checked_atomically(self):
        before = (self.run / "state.json").read_bytes()
        with self.assertRaises(sv.StateError):
            self.worker({"todos": {"execute": self.item("execute")}})
        missing_evidence = self.item("plan")
        missing_evidence["evidence"] = []
        with self.assertRaises(sv.StateError):
            self.parent({"todos": {"plan": missing_evidence}})
        self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_cycles_and_incomplete_waits_rejected(self):
        cycle = self.item("plan", "todo")
        cycle["depends_on"] = ["execute"]
        for item in (cycle, self.item("plan", "waiting")):
            with self.subTest(item=item), self.assertRaises(sv.StateError):
                self.parent({"todos": {"plan": item}})

    def test_rework_and_standard_completion_reuse_run_without_goal_close_message(self):
        self.prepare()
        self.parent({"recovery": self.recovery()})
        self.complete_execution()
        self.parent({"resume_worker": True, "request_id": "review:r1", "decision": "一次修复 M1 和 M2",
                     "resolution": self.resolution("worker_retry", "review:execute")})
        self.worker({"state": "running", "writes_paused": False, "last_applied_request_id": "review:r1",
                     "todos": {"execute": self.item("execute", "running")}})
        self.complete_execution()
        self.parent({"todos": {"review": self.item("review")}})
        self.parent({"todos": {"close": self.item("close")}, "state": "accepted"})
        result = sv.check_run(self.run, now=START + dt.timedelta(days=1), force=True)
        self.assertEqual(result["run_id"], self.initial["run_id"])
        self.assertEqual(result["action"], "closed")
        self.assertFalse(result["due"])
        self.assertEqual(result["pending_todos"], [])
        self.assertEqual(self.state()["worker"]["applied_request_ids"], ["review:r1"])

    def test_pending_todos_and_unfinished_jobs_prevent_acceptance(self):
        self.prepare()
        with self.assertRaises(sv.StateError):
            self.parent({"state": "accepted"})
        self.complete_execution()
        self.parent({"todos": {"review": self.item("review"), "close": self.item("close")}})
        self.worker({"jobs": [{"job_id": "job", "kind": "local", "write_scope": [], "status": "running"}]})
        with self.assertRaises(sv.StateError):
            self.parent({"state": "accepted"})
        with self.assertRaises(sv.StateError):
            self.parent({"state": "cancelled"})
        self.worker({"jobs": [{"job_id": "job", "kind": "local", "write_scope": [], "status": "stopped"}]})
        self.parent({"state": "cancelled"})
        self.assertEqual(sv.check_run(self.run, now=START)["action"], "closed")

    def test_cancel_refuses_live_or_unknown_jobs_without_sealing_cleanup_updates(self):
        self.prepare()
        for status in ("running", "unknown"):
            self.worker({"state": "running", "writes_paused": True,
                         "jobs": [{"job_id": "cleanup-job", "kind": "local",
                                   "write_scope": [], "status": status}]})
            before = (self.run / "state.json").read_bytes()
            with self.subTest(status=status), self.assertRaises(sv.StateError):
                self.parent({"state": "cancelled"})
            self.assertEqual((self.run / "state.json").read_bytes(), before)
        self.worker({"writes_paused": False, "jobs": []})
        with self.assertRaises(sv.StateError):
            self.parent({"state": "cancelled"})
        self.worker({"writes_paused": True, "jobs": [
            {"job_id": "cleanup-job", "kind": "local", "write_scope": [], "status": "stopped"}]})
        self.parent({"state": "cancelled"})
        self.assertEqual(self.state()["worker"]["jobs"][0]["status"], "stopped")
        with self.assertRaises(sv.StateError):
            self.worker({"summary": "迟到写入"})

    def test_legacy_run_is_not_migrated_by_read_or_new_fields(self):
        other = Path(self.temp.name) / "legacy"
        sv.init_run(other, worker_target="legacy", objective="目标", now=START)
        before = (other / "state.json").read_bytes()
        self.assertNotIn("mode", sv.check_run(other, now=START))
        with self.assertRaises(sv.StateError):
            sv.update_parent(other, {"recovery": self.recovery()}, now=START)
        self.assertEqual((other / "state.json").read_bytes(), before)
