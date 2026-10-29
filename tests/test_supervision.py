"""运行：python3 -m unittest discover -s tests -p 'test_supervision.py' -v。"""

import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "dual-session-exec" / "scripts" / "supervision.py"
SPEC = importlib.util.spec_from_file_location("luna_supervision", SCRIPT)
sv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sv)
START = dt.datetime(2026, 9, 10, 0, 0, tzinfo=dt.timezone.utc)


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luna-supervision-test-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        self.initial = sv.init_run(self.run, worker_target="/root/luna_worker", objective="完成已批准方案", now=START)

    def at(self, minutes=0, seconds=0):
        return START + dt.timedelta(minutes=minutes, seconds=seconds)

    def worker(self, patch=None, at=0):
        return sv.update_worker(self.run, {} if patch is None else patch, now=self.at(at))

    def parent(self, patch=None, at=0):
        return sv.update_parent(self.run, {} if patch is None else patch, now=self.at(at))

    def check(self, at=0, force=False):
        return sv.check_run(self.run, now=self.at(at), force=force)

    def running(self, at=0):
        self.worker({"state": "running", "phase": "验证", "summary": "正在验证修改", "progress": "已完成实现"}, at=at)

    def blocker(self, attempts=None, first_seen=0):
        return {"issue_id": "compile-01", "request_id": "compile-01:r1", "reason": "编译错误", "first_seen_at": sv.iso(self.at(first_seen)),
                "attempts": attempts or [], "requested_help": "请诊断依赖关系"}

    def test_initial_state_and_identity(self):
        self.assertEqual(self.initial["version"], 1)
        self.assertIsNone(self.initial["identity"]["parent_thread_id"])
        self.assertIsNone(self.initial["identity"]["worker_thread_id"])
        self.assertEqual(self.initial["policy"]["check_minutes"], 30)
        self.assertEqual(self.initial["parent"]["next_check_at"], sv.iso(self.at(30)))
        self.assertIsNone(self.initial["worker"]["last_progress_at"])
        self.assertIsNone(self.check()["parent_thread_id"])

    def test_normal_progress_and_exact_check_boundary(self):
        self.running(at=10)
        self.assertEqual(self.check(at=29.999)["action"], "not_due")
        result = self.check(at=30)
        self.assertTrue(result["due"])
        self.assertEqual(result["action"], "continue")
        self.assertFalse(self.check(at=29.999)["due"])

    def test_refresh_does_not_reset_progress(self):
        self.running(at=0)
        self.worker({"summary": "仍在排查", "progress": "  "}, at=29)
        state = sv.load_state(self.run / "state.json")
        self.assertEqual(state["worker"]["last_progress_at"], sv.iso(START))
        self.assertEqual(state["worker"]["updated_at"], sv.iso(self.at(29)))
        self.assertEqual(self.check(at=30)["action"], "request_status")
        self.worker({"progress": "已通过关键验证"}, at=31)
        self.assertEqual(self.check(at=31)["action"], "continue")

    def test_check_is_readonly_and_parent_moves_schedule_only_when_completed(self):
        original = (self.run / "state.json").read_bytes()
        before_files = set(self.run.iterdir())
        self.check(at=30)
        self.check(at=31, force=True)
        self.assertEqual((self.run / "state.json").read_bytes(), original)
        self.assertEqual(set(self.run.iterdir()), before_files)
        self.parent({"decision": "准备核查"}, at=31)
        self.assertEqual(self.check(at=31)["next_check_at"], sv.iso(self.at(30)))
        self.parent({"check_completed": False}, at=32)
        self.assertEqual(self.check(at=32)["next_check_at"], sv.iso(self.at(30)))
        self.parent({"decision": "已完成核查", "check_completed": True}, at=33)
        result = self.check(at=33)
        self.assertEqual(result["last_checked_at"], sv.iso(self.at(33)))
        self.assertEqual(result["next_check_at"], sv.iso(self.at(63)))
        self.assertFalse(result["due"])

    def test_long_external_operation_can_have_old_worker_update(self):
        self.worker({"state": "waiting_external", "phase": "训练", "summary": "GPU 实验运行中",
                     "expected_until": sv.iso(self.at(120)), "evidence": ["作业 42 第 10 轮完成"]})
        self.assertEqual(self.check(at=60)["action"], "continue")
        self.assertEqual(self.check(at=119)["action"], "continue")
        self.assertEqual(self.check(at=120)["action"], "investigate")
        self.assertEqual(self.check(at=121)["action"], "investigate")

    def test_external_wait_requires_both_time_and_evidence(self):
        for expected, evidence in [(None, ["有日志"]), (sv.iso(self.at(60)), []), (None, [])]:
            with self.subTest(expected=expected, evidence=evidence):
                self.worker({"state": "waiting_external", "expected_until": expected, "evidence": evidence})
                self.assertEqual(self.check(at=30)["action"], "investigate")

    def test_two_different_failed_methods_escalate_before_due(self):
        attempts = [{"method": "检查依赖", "result": "failed"}, {"method": "最小复现", "result": "failed"}]
        self.worker({"blocker": self.blocker(attempts)})
        result = self.check(at=1)
        self.assertFalse(result["due"])
        self.assertEqual(result["action"], "help")

    def test_duplicate_or_nonfailed_attempts_do_not_trigger_count(self):
        cases = [[{"method": "rebuild", "result": "failed"}, {"method": " REBUILD ", "result": "failed"}],
                 [{"method": "方法一", "result": "failed"}, {"method": "方法二", "result": "succeeded"}],
                 [{"method": "方法一", "result": "failed"}, {"method": "方法二", "result": "inconclusive"}]]
        for attempts in cases:
            with self.subTest(attempts=attempts):
                self.worker({"blocker": None})
                self.worker({"blocker": self.blocker(attempts)})
                self.assertEqual(self.check(at=1)["action"], "not_due")

    def test_fifteen_minute_escalation_exact_boundary_before_due(self):
        self.worker({"blocker": self.blocker()})
        self.assertEqual(self.check(at=14.999)["action"], "not_due")
        result = self.check(at=15)
        self.assertEqual(result["action"], "help")
        self.assertFalse(result["due"])

    def test_guidance_consumption_resets_only_current_repair_window(self):
        attempts = [{"method": "检查依赖", "result": "failed"}, {"method": "最小复现", "result": "failed"}]
        self.worker({"blocker": self.blocker(attempts)}, at=0)
        self.assertEqual(self.check(at=16)["action"], "help")
        self.parent({"state": "helping", "request_id": "compile-01:r1", "decision": "正在诊断"}, at=16)
        self.parent({"state": "watching", "request_id": "compile-01:r1", "decision": "请根据主代理修复重新验证"}, at=17)
        self.worker({"state": "running", "summary": "按指导验证", "last_applied_request_id": "compile-01:r1"}, at=18)
        result = self.check(at=19)
        self.assertEqual(result["action"], "not_due")
        self.assertEqual(result["blocker"]["first_seen_at"], sv.iso(START))
        self.assertEqual(result["repair_round"]["decision_applied_at"], sv.iso(self.at(18)))
        self.assertEqual(result["repair_round"]["attempts_baseline_count"], 2)
        self.worker({"summary": "例行刷新，仍在验证"}, at=29)
        self.assertEqual(self.check(at=29)["repair_round"], result["repair_round"])
        self.assertNotEqual(self.check(at=32.999)["action"], "help")
        self.assertEqual(self.check(at=33)["action"], "help")

    def test_guidance_requires_parent_matching_identity_and_explicit_decision(self):
        self.worker({"blocker": self.blocker()})
        for patch in ({}, {"request_id": "different", "decision": "重试"},
                      {"request_id": "compile-01:r1", "decision": None},
                      {"request_id": "compile-01:r1", "decision": "重试", "state": "awaiting_user"},
                      {"request_id": "compile-01:r1", "decision": "重试", "state": "helping"}):
            with self.subTest(patch=patch):
                self.parent(patch)
                with self.assertRaises(sv.StateError):
                    self.worker({"last_applied_request_id": "compile-01:r1"})

    def test_old_resume_cannot_be_consumed_twice_or_cleared(self):
        self.worker({"blocker": self.blocker()})
        self.parent({"request_id": "compile-01:r1", "decision": "按指导验证"})
        self.worker({"last_applied_request_id": "compile-01:r1"}, at=1)
        with self.assertRaises(sv.StateError):
            self.worker({"last_applied_request_id": "compile-01:r1"}, at=2)
        with self.assertRaises(sv.StateError):
            self.worker({"last_applied_request_id": None}, at=2)
        blocker = dict(self.blocker(), request_id="compile-01:r2")
        self.worker({"blocker": blocker})
        self.parent({"request_id": "compile-01:r2", "decision": "第二轮指导"})
        self.worker({"last_applied_request_id": "compile-01:r2"}, at=3)
        self.parent({"request_id": "compile-01:r1", "decision": "迟到的旧指导"}, at=4)
        with self.assertRaises(sv.StateError):
            self.worker({"last_applied_request_id": "compile-01:r1"}, at=4)
        self.assertEqual(self.check(at=4)["last_applied_request_id"], "compile-01:r2")

    def test_new_failed_methods_after_guidance_trigger_new_request(self):
        attempts = [{"method": "方法一", "result": "failed"}, {"method": "方法二", "result": "failed"}]
        self.worker({"blocker": self.blocker(attempts)})
        self.parent({"request_id": "compile-01:r1", "decision": "检查新的两种假设"})
        self.worker({"last_applied_request_id": "compile-01:r1"}, at=1)
        attempts = attempts + [{"method": "方法三", "result": "failed"}]
        self.worker({"blocker": self.blocker(attempts)}, at=2)
        self.assertEqual(self.check(at=2)["action"], "not_due")
        attempts = attempts + [{"method": "方法四", "result": "failed"}]
        blocker = dict(self.blocker(attempts), request_id="compile-01:r2")
        self.worker({"blocker": blocker}, at=3)
        self.assertEqual(self.check(at=3)["action"], "help")
        self.assertEqual(self.check(at=3)["repair_round"]["request_id"], "compile-01:r1")
        self.parent({"request_id": "compile-01:r2", "decision": "第二轮指导"}, at=4)
        self.worker({"last_applied_request_id": "compile-01:r2"}, at=5)
        self.assertEqual(self.check(at=6)["action"], "not_due")

    def test_ordinary_issue_refresh_cannot_reset_history_or_elapsed_time(self):
        attempts = [{"method": "方法一", "result": "failed"}]
        original = self.blocker(attempts)
        self.worker({"blocker": original})
        for blocker in (dict(original, first_seen_at=sv.iso(self.at(10))),
                        dict(original, attempts=[]),
                        dict(original, attempts=[{"method": "方法二", "result": "failed"}])):
            with self.subTest(blocker=blocker), self.assertRaises(sv.StateError):
                self.worker({"blocker": blocker}, at=10)
        self.worker({"blocker": dict(original, request_id="compile-01:r2")}, at=14)
        self.assertEqual(self.check(at=15)["action"], "help")
        with self.assertRaises(sv.StateError):
            self.worker({"repair_round": None})
        with self.assertRaises(sv.StateError):
            self.worker({"applied_request_ids": []})

    def test_review_requires_paused_writes(self):
        with self.assertRaises(sv.StateError):
            self.worker({"state": "ready_for_review"})
        self.worker({"state": "ready_for_review", "writes_paused": True})
        self.assertEqual(self.check()["action"], "review")
        with self.assertRaises(sv.StateError):
            self.worker({"writes_paused": False})

    def test_immediate_needs_parent_and_review(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.assertEqual(self.check(at=1)["action"], "help")
        self.parent({"request_id": "compile-01:r1", "decision": "已解决，可以提交独立验收"}, at=2)
        self.worker({"state": "ready_for_review", "last_applied_request_id": "compile-01:r1"}, at=2)
        self.assertEqual(self.check(at=2)["action"], "review")

    def test_review_cannot_resume_without_consuming_parent_guidance(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        before = (self.run / "state.json").read_bytes()
        for patch in ({"state": "running"}, {"state": "waiting_external"},
                      {"state": "running", "writes_paused": False}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.worker(patch)
            self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_review_guidance_without_blocker_resumes_once(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        self.parent({"state": "helping", "request_id": "review-p0:r1", "decision": "正在验收"})
        self.parent({"resume_worker": True, "request_id": "review-p0:r1", "decision": "P0 通过，继续 P1"})
        result = self.worker({"state": "running", "writes_paused": False,
                              "last_applied_request_id": "review-p0:r1"}, at=1)
        self.assertEqual(result["worker"]["applied_request_ids"], ["review-p0:r1"])
        self.assertIsNone(result["worker"]["repair_round"])
        with self.assertRaises(sv.StateError):
            self.worker({"last_applied_request_id": "review-p0:r1"}, at=2)

    def test_review_guidance_rejects_mismatched_or_locked_parent(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        for parent in ({"request_id": "wrong", "decision": "继续"},
                       {"request_id": "review:r1", "decision": "继续", "state": "helping"},
                       {"request_id": "review:r1", "decision": "继续", "state": "awaiting_user"}):
            self.parent(parent)
            with self.subTest(parent=parent), self.assertRaises(sv.StateError):
                self.worker({"state": "running", "last_applied_request_id": "review:r1"})

    def test_review_rework_and_final_receipt_stay_in_one_run(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        self.parent({"resume_worker": True, "request_id": "review:r1", "decision": "验收不通过，补充缺失验证"})
        self.worker({"state": "running", "writes_paused": False, "last_applied_request_id": "review:r1"})
        self.worker({"state": "ready_for_review", "writes_paused": True, "progress": "补齐验证"})
        self.parent({"resume_worker": True, "request_id": "review:r2", "decision": "最终验收通过，仅关闭目标并退出"})
        state = self.worker({"last_applied_request_id": "review:r2"})
        self.assertEqual(state["run_id"], self.initial["run_id"])
        self.assertTrue(state["worker"]["writes_paused"])
        self.assertEqual(state["worker"]["state"], "ready_for_review")
        self.parent({"state": "accepted"})
        self.assertEqual(self.check(at=300)["action"], "closed")
        self.assertFalse(self.check(at=300)["due"])

    def test_needs_parent_cannot_resume_without_consuming_matching_guidance(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        before = (self.run / "state.json").read_bytes()
        for next_state in ("running", "waiting_external", "ready_for_review", "starting"):
            with self.subTest(state=next_state), self.assertRaises(sv.StateError):
                self.worker({"state": next_state})
            self.assertEqual((self.run / "state.json").read_bytes(), before)
        self.parent({"request_id": "compile-01:r1", "decision": "请重新验证"})
        with self.assertRaises(sv.StateError):
            self.worker({"state": "running", "writes_paused": False})
        with self.assertRaises(sv.StateError):
            self.worker({"writes_paused": False})
        self.worker({"state": "running", "writes_paused": False, "last_applied_request_id": "compile-01:r1"})
        self.assertEqual(self.check()["worker_state"], "running")

    def test_needs_parent_can_resume_after_separately_consuming_guidance(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"request_id": "compile-01:r1", "decision": "请验证修复"})
        self.worker({"last_applied_request_id": "compile-01:r1"}, at=1)
        self.worker({"state": "waiting_external", "writes_paused": False}, at=2)
        self.assertEqual(self.check(at=2)["worker_state"], "waiting_external")

    def test_consuming_guidance_can_clear_resolved_blocker_in_same_update(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"request_id": "compile-01:r1", "decision": "问题已修复，可以继续"})
        self.worker({"state": "running", "writes_paused": False, "last_applied_request_id": "compile-01:r1", "blocker": None}, at=1)
        state = sv.load_state(self.run / "state.json")
        self.assertIsNone(state["worker"]["blocker"])
        self.assertIsNone(state["worker"]["repair_round"])
        self.assertEqual(state["worker"]["last_applied_request_id"], "compile-01:r1")
        self.assertEqual(state["worker"]["applied_request_ids"], ["compile-01:r1"])
        self.assertEqual(state["worker"]["state"], "running")

    def test_old_or_changed_request_cannot_resume_new_help_round(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"request_id": "compile-01:r1", "decision": "第一轮指导"})
        self.worker({"state": "running", "last_applied_request_id": "compile-01:r1"}, at=1)
        second = dict(self.blocker(), request_id="compile-01:r2")
        self.worker({"state": "needs_parent", "blocker": second}, at=2)
        for patch in ({"state": "running"}, {"state": "running", "blocker": self.blocker()},
                      {"state": "running", "blocker": None}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.worker(patch, at=3)
        self.parent({"request_id": "compile-01:r2", "decision": "第二轮指导"}, at=3)
        with self.assertRaises(sv.StateError):
            self.worker({"state": "running"}, at=4)
        self.worker({"state": "running", "last_applied_request_id": "compile-01:r2"}, at=4)
        self.assertEqual(self.check(at=4)["last_applied_request_id"], "compile-01:r2")

    def test_parent_helping_or_awaiting_user_rejects_resume_but_accepts_observations(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"request_id": "compile-01:r1", "decision": "曾给出指导"})
        self.worker({"last_applied_request_id": "compile-01:r1"})
        jobs = [{"job_id": "remote:cluster:job-42:started-at-00:00", "kind": "remote_job",
                 "write_scope": ["work/output"], "status": "running"}]
        for state in ("helping", "awaiting_user"):
            self.parent({"state": state})
            for patch in ({"state": "running"}, {"state": "waiting_external"},
                          {"state": "ready_for_review"}, {"writes_paused": False}):
                with self.subTest(parent=state, patch=patch), self.assertRaises(sv.StateError):
                    self.worker(patch)
            self.worker({"summary": "保持求助状态；远端任务仍在运行", "evidence": ["已核实远端日志更新"], "jobs": jobs})
            self.assertEqual(self.check()["jobs"], jobs)
            self.assertEqual(self.check()["worker_state"], "needs_parent")

    def test_parent_helping_rejects_resuming_other_paused_worker(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        self.parent({"state": "helping"})
        for patch in ({"state": "running"}, {"state": "waiting_external"}, {"writes_paused": False}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.worker(patch)
        self.worker({"summary": "保持暂停，等待主代理处理"})

    def test_resume_worker_releases_parent_lock_before_bounded_repair(self):
        self.worker({"state": "ready_for_review", "writes_paused": True})
        self.parent({"state": "helping", "request_id": "compile-01:r1", "decision": "独立复核"})
        # 复现：主代理已派发修正，但 helping 仍锁住 worker。
        with self.assertRaises(sv.StateError):
            self.worker({"state": "running", "writes_paused": False})
        released = self.parent({"resume_worker": True, "request_id": "compile-01:r1",
                                "decision": "仅修复已定位缺陷并验证"}, at=1)
        self.assertEqual(released["parent"]["state"], "watching")
        self.assertEqual(released["parent"]["next_check_at"], sv.iso(self.at(31)))
        self.worker({"blocker": self.blocker()})
        self.worker({"state": "running", "writes_paused": False,
                     "last_applied_request_id": "compile-01:r1"}, at=2)
        self.worker({"state": "ready_for_review", "writes_paused": True, "blocker": None}, at=3)
        self.assertEqual(self.check(at=3)["action"], "review")
        self.parent({"state": "accepted"}, at=4)
        self.assertEqual(self.check(at=60)["action"], "closed")
        self.assertFalse(self.check(at=60)["due"])

    def test_resume_worker_validates_guidance_before_changing_state(self):
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"state": "helping"})
        before = (self.run / "state.json").read_bytes()
        guidance = {"resume_worker": True, "request_id": "compile-01:r1", "decision": "执行修复"}
        bad = [{"resume_worker": True}, dict(guidance, decision="  "),
               dict(guidance, request_id="different"), dict(guidance, state="helping"),
               dict(guidance, state="accepted"), dict(guidance, check_completed=False),
               dict(guidance, resume_worker="true")]
        for patch in bad:
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.parent(patch)
            self.assertEqual((self.run / "state.json").read_bytes(), before)
        state = self.parent(guidance)
        self.assertEqual(state["parent"]["state"], "watching")
        self.worker({"state": "running", "writes_paused": False,
                     "last_applied_request_id": "compile-01:r1"})

    def test_resume_worker_cannot_revive_terminal_or_replay_consumed_instruction(self):
        guidance = {"resume_worker": True, "request_id": "compile-01:r1", "decision": "执行修复"}
        self.worker({"state": "needs_parent", "writes_paused": True, "blocker": self.blocker()})
        self.parent(guidance)
        self.worker({"state": "running", "last_applied_request_id": "compile-01:r1"})
        with self.assertRaises(sv.StateError):
            self.parent(guidance)
        self.parent({"state": "cancelled"})
        with self.assertRaises(sv.StateError):
            self.parent(dict(guidance, request_id="compile-01:r2"))

    def test_awaiting_user_and_helping_take_priority(self):
        self.worker({"state": "ready_for_review", "writes_paused": True, "blocker": self.blocker()})
        self.parent({"state": "awaiting_user", "request_id": "question-1"})
        self.assertEqual(self.check(at=1, force=True)["action"], "await_user")
        self.assertEqual(self.check(at=300)["action"], "await_user")
        self.parent({"state": "helping"}, at=301)
        self.assertEqual(self.check(at=302)["action"], "parent_helping")

    def test_accepted_and_cancelled_are_terminal_and_reject_late_writes(self):
        for terminal in ("accepted", "cancelled"):
            with self.subTest(terminal=terminal):
                folder = Path(self.temp.name) / terminal
                sv.init_run(folder, worker_target="/root/luna_worker", objective="目标", now=START)
                sv.update_parent(folder, {"state": terminal}, now=START)
                before = (folder / "state.json").read_bytes()
                self.assertEqual(sv.check_run(folder, now=self.at(1), force=True)["action"], "closed")
                with self.assertRaises(sv.StateError):
                    sv.update_worker(folder, {"state": "running"}, now=self.at(2))
                with self.assertRaises(sv.StateError):
                    sv.update_parent(folder, {"state": "watching"}, now=self.at(2))
                self.assertEqual((folder / "state.json").read_bytes(), before)

    def test_identity_binding_cannot_switch_or_clear(self):
        self.parent({"parent_thread_id": "parent-01", "worker_thread_id": "worker-01"})
        self.parent({"parent_thread_id": "parent-01", "worker_thread_id": "worker-01"})
        for key in ("parent_thread_id", "worker_thread_id"):
            for value in ("different-id", None):
                with self.subTest(key=key, value=value), self.assertRaises(sv.StateError):
                    self.parent({key: value})
        result = self.check()
        self.assertEqual(result["parent_thread_id"], "parent-01")
        self.assertEqual(result["worker_thread_id"], "worker-01")
        self.assertEqual(result["worker_target"], "/root/luna_worker")

    def test_terminal_run_has_no_scheduled_check_even_when_forced(self):
        self.parent({"state": "accepted", "check_completed": True}, at=1)
        state = sv.load_state(self.run / "state.json")
        self.assertIsNone(state["parent"]["next_check_at"])
        for force in (False, True):
            result = self.check(at=300, force=force)
            self.assertEqual(result["action"], "closed")
            self.assertFalse(result["due"])
            self.assertIsNone(result["next_check_at"])

    def test_old_terminal_record_ignores_leftover_deadline_without_rewriting(self):
        self.parent({"state": "cancelled"})
        path = self.run / "state.json"
        state = json.loads(path.read_text())
        state["parent"]["next_check_at"] = sv.iso(self.at(30))
        path.write_text(json.dumps(state))
        before = path.read_bytes()
        result = self.check(at=300)
        self.assertEqual(result["action"], "closed")
        self.assertFalse(result["due"])
        self.assertIsNone(result["next_check_at"])
        self.assertEqual(path.read_bytes(), before)

    def test_closed_run_exposes_heartbeat_and_can_record_cleanup_without_reopening(self):
        self.parent({"automation_id": "heartbeat-this-run", "state": "accepted"})
        self.assertEqual(self.check(at=300)["automation_id"], "heartbeat-this-run")
        before = (self.run / "state.json").read_bytes()
        for patch in ({"automation_id": "another-heartbeat"},
                      {"automation_id": None, "state": "watching"},
                      {"automation_id": None, "check_completed": True}):
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.parent(patch)
            self.assertEqual((self.run / "state.json").read_bytes(), before)
        self.parent({"automation_id": None}, at=301)
        self.parent({"automation_id": None}, at=302)
        self.assertIsNone(self.check(at=303)["automation_id"])
        self.assertEqual(self.check(at=303)["action"], "closed")
        self.assertFalse(self.check(at=303)["due"])
        with self.assertRaises(sv.StateError):
            self.worker({"state": "running"}, at=304)

    def test_active_record_still_requires_a_deadline(self):
        path = self.run / "state.json"
        state = json.loads(path.read_text())
        state["parent"]["next_check_at"] = None
        path.write_text(json.dumps(state))
        with self.assertRaises(sv.StateError):
            self.check()

    def test_repeated_init_preserves_state(self):
        before = (self.run / "state.json").read_bytes()
        with self.assertRaises(sv.StateError):
            sv.init_run(self.run, worker_target="replacement", objective="不同目标", now=START)
        self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_force_bypasses_time_only(self):
        self.running(at=1)
        result = self.check(at=2, force=True)
        self.assertFalse(result["due"])
        self.assertTrue(result["forced"])
        self.assertEqual(result["action"], "continue")

    def test_starting_and_stale_status_request_update(self):
        self.assertEqual(self.check(at=30)["action"], "request_status")
        self.running(at=1)
        self.assertEqual(self.check(at=31)["action"], "request_status")

    def test_jobs_are_validated_and_preserved_without_process_actions(self):
        jobs = [{"job_id": "local:host:pid-42:start-2026-09-10T00:00Z", "kind": "local_process",
                 "pid": 42, "write_scope": ["work/experiment"], "status": "running"}]
        self.worker({"jobs": jobs, "writes_paused": True})
        self.assertEqual(self.check()["jobs"], jobs)
        self.assertTrue(self.check()["writes_paused"])
        for bad_job in [dict(jobs[0], status="killed"), dict(jobs[0], pid=True), dict(jobs[0], mystery=1),
                        dict(jobs[0], write_scope="work/experiment")]:
            with self.subTest(job=bad_job), self.assertRaises(sv.StateError):
                self.worker({"jobs": [bad_job]})

    def test_invalid_worker_inputs_do_not_modify_state(self):
        before = (self.run / "state.json").read_bytes()
        bad = [[], {"unknown": 1}, {"parent": {}}, {"state": "blocked"}, {"writes_paused": "true"},
               {"progress": None}, {"progress": 4}, {"evidence": [None]}, {"evidence": [""]},
               {"expected_until": "2026-09-10T00:00:00"}, {"expected_until": "0001-01-01T00:00:00+23:00"}, {"updated_at": sv.iso(START)},
               {"blocker": {"reason": "缺少字段"}}, {"jobs": ["not-object"]},
               {"blocker": dict(self.blocker(), attempts=[{"method": "方法", "result": "失败"}])}]
        for patch in bad:
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.worker(patch)
            self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_invalid_parent_inputs_do_not_modify_state(self):
        bad = [{"state": "running"}, {"check_completed": 1}, {"worker_thread_id": ""},
               {"decision": {}}, {"last_checked_at": sv.iso(START)}, {"worker": {}}]
        before = (self.run / "state.json").read_bytes()
        for patch in bad:
            with self.subTest(patch=patch), self.assertRaises(sv.StateError):
                self.parent(patch)
            self.assertEqual((self.run / "state.json").read_bytes(), before)

    def test_invalid_policies(self):
        for key, value in [("check_minutes", 0), ("stalled_minutes", -1), ("repair_minutes", True),
                           ("check_minutes", float("nan")), ("check_minutes", float("inf")),
                           ("max_repair_attempts", 1.5), ("max_repair_attempts", False),
                           ("check_minutes", 10 ** 500)]:
            with self.subTest(key=key, value=value), self.assertRaises(sv.StateError):
                sv.init_run(Path(self.temp.name) / "invalid", worker_target="worker", objective="目标", **{key: value}, now=START)

    def test_timezone_required_and_normalized(self):
        with self.assertRaises(sv.StateError):
            self.worker({"expected_until": "2026-09-10T12:00:00"})
        self.worker({"expected_until": "2026-09-10T12:00:00+08:00"})
        self.assertEqual(sv.timestamp("2026-09-10T12:00:00+08:00", "time"), self.at(240))
        with self.assertRaises(sv.StateError):
            sv.check_run(self.run, now=dt.datetime(2026, 9, 10))

    def test_corrupt_state_never_silently_rebuilt(self):
        path = self.run / "state.json"
        for content in ("not-json", "{}", "[]", '{"version":1,"version":1}', '{"a":NaN}'):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(sv.StateError):
                    self.check()
                with self.assertRaises(sv.StateError):
                    self.worker({"summary": "不能覆盖损坏状态"})
                with self.assertRaises(sv.StateError):
                    sv.init_run(self.run, worker_target="worker", objective="目标", now=START)
                self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_missing_record_or_lock_is_error(self):
        with self.assertRaises(sv.StateError):
            sv.check_run(Path(self.temp.name) / "missing", now=START)
        (self.run / ".state.lock").unlink()
        with self.assertRaises(sv.StateError):
            self.check()

    def test_atomic_failure_preserves_existing_json_and_cleans_temp(self):
        before = (self.run / "state.json").read_bytes()
        with mock.patch.object(sv.os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                self.worker({"summary": "不应落盘"})
        self.assertEqual((self.run / "state.json").read_bytes(), before)
        self.assertEqual(list(self.run.glob(".state-*.tmp")), [])

    def test_concurrent_parent_worker_updates_preserve_both_domains_and_complete_json(self):
        code = "\n".join([
            "import sys", "sys.path.insert(0, sys.argv[1])", "import supervision as s",
            "for i in range(35):", "    patch = {'summary': 'worker-' + str(i)} if sys.argv[3] == 'worker' else {'decision': 'parent-' + str(i)}",
            "    fn = s.update_worker if sys.argv[3] == 'worker' else s.update_parent", "    fn(sys.argv[2], patch)",
        ])
        processes = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPT.parent), str(self.run), role],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                     for role in ("worker", "parent")]
        reads = 0
        try:
            while any(process.poll() is None for process in processes):
                state = json.loads((self.run / "state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["run_id"], self.initial["run_id"])
                self.assertIn("worker", state)
                self.assertIn("parent", state)
                reads += 1
            for process in processes:
                _, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        final = sv.load_state(self.run / "state.json")
        self.assertGreater(reads, 0)
        self.assertEqual(final["worker"]["summary"], "worker-34")
        self.assertEqual(final["parent"]["decision"], "parent-34")

    def test_cli_help_json_and_invalid_input_errors(self):
        def cli(*args):
            return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
        self.assertEqual(cli("--help").returncode, 0)
        for command in ("init", "worker", "parent", "check"):
            self.assertEqual(cli(command, "--help").returncode, 0)
        result = cli("check", "--run-dir", str(self.run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["run_id"], self.initial["run_id"])
        patch_file = Path(self.temp.name) / "input.json"
        for content in ('{"summary":', '{"summary":"一","summary":"二"}', '{"progress":NaN}', '[1,2]'):
            patch_file.write_text(content, encoding="utf-8")
            result = cli("worker", "--run-dir", str(self.run), "--input", str(patch_file))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("错误：", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")
        patch_file.write_text(json.dumps({"state": "running", "summary": "开始验证", "progress": "完成实现"}, ensure_ascii=False), encoding="utf-8")
        result = cli("worker", "--run-dir", str(self.run), "--input", str(patch_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["worker"]["last_progress"], "完成实现")


if __name__ == "__main__":
    unittest.main()
