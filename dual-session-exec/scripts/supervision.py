#!/usr/bin/env python3
"""双会话协作记账：原子保存状态，只建议检查动作，不管理代理或进程。"""

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import uuid


UTC = dt.timezone.utc
WORKER_STATES = {"starting", "running", "waiting_external", "needs_parent", "ready_for_review"}
PARENT_STATES = {"watching", "helping", "awaiting_user", "accepted", "cancelled"}
TERMINAL = {"accepted", "cancelled"}
JOB_STATES = {"running", "stopped", "completed", "unknown"}
RESULTS = {"failed", "succeeded", "inconclusive"}
BLOCKER_KINDS = {"repair", "decision"}
RESOLUTION_MODES = {"continue", "worker_retry", "parent_takeover"}
WORKER_FIELDS = {"state", "phase", "summary", "evidence", "jobs", "expected_until", "writes_paused", "blocker", "last_applied_request_id"}
PARENT_FIELDS = {"state", "decision", "request_id", "automation_id"}


class StateError(ValueError):
    """可直接显示给用户的输入或状态错误。"""


def fail(message):
    raise StateError(message)


def fields(value, allowed, label, required=()):
    if not isinstance(value, dict):
        fail(f"{label} 必须是 JSON 对象")
    unknown = set(value) - set(allowed)
    missing = set(required) - set(value)
    if unknown:
        fail(f"{label} 存在未知字段：{', '.join(sorted(unknown))}")
    if missing:
        fail(f"{label} 缺少字段：{', '.join(sorted(missing))}")


def string(value, label, nullable=False, nonempty=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or (nonempty and not value.strip()):
        fail(f"{label} 必须是{'非空' if nonempty else ''}字符串")


def boolean(value, label):
    if not isinstance(value, bool):
        fail(f"{label} 必须是布尔值")


def choices(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        fail(f"{label} 必须是：{', '.join(sorted(allowed))}")


def positive(value, label, integer=False):
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or (isinstance(value, float) and not math.isfinite(value)) or value <= 0:
        fail(f"{label} 必须是正{'整数' if integer else '数'}")
    try:
        dt.timedelta(minutes=value)
    except OverflowError:
        fail(f"{label} 超出可表示的时间范围")


def timestamp(value, label, nullable=False):
    if nullable and value is None:
        return None
    string(value, label, nonempty=True)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{label} 必须是带时区的 ISO 8601 时间")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{label} 必须包含时区")
    try:
        return parsed.astimezone(UTC)
    except OverflowError:
        fail(f"{label} 转换为 UTC 后超出可表示范围")


def now_utc(now=None):
    value = now if now is not None else dt.datetime.now(UTC)
    if not isinstance(value, dt.datetime) or value.tzinfo is None or value.utcoffset() is None:
        fail("now 必须是带时区的 datetime")
    return value.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def strings(value, label):
    if not isinstance(value, list):
        fail(f"{label} 必须是字符串列表")
    for item in value:
        string(item, label, nonempty=True)


def validate_jobs(value):
    if not isinstance(value, list):
        fail("jobs 必须是对象列表")
    seen = set()
    for job in value:
        fields(job, {"job_id", "kind", "pid", "write_scope", "status"}, "job", {"job_id", "kind", "write_scope", "status"})
        string(job["job_id"], "job.job_id", nonempty=True)
        string(job["kind"], "job.kind", nonempty=True)
        if job["job_id"] in seen:
            fail("jobs 中 job_id 不得重复")
        seen.add(job["job_id"])
        if job.get("pid") is not None:
            positive(job["pid"], "job.pid", integer=True)
        strings(job["write_scope"], "job.write_scope")
        choices(job["status"], JOB_STATES, "job.status")


def validate_blocker(value):
    if value is None:
        return
    required = {"issue_id", "request_id", "reason", "first_seen_at", "attempts", "requested_help"}
    fields(value, required | {"kind"}, "blocker", required)
    for key in ("issue_id", "request_id", "reason", "requested_help"):
        string(value[key], f"blocker.{key}", nonempty=True)
    timestamp(value["first_seen_at"], "blocker.first_seen_at")
    if "kind" in value:
        choices(value["kind"], BLOCKER_KINDS, "blocker.kind")
    if not isinstance(value["attempts"], list):
        fail("blocker.attempts 必须是对象列表")
    for attempt in value["attempts"]:
        fields(attempt, {"method", "result"}, "attempt", {"method", "result"})
        string(attempt["method"], "attempt.method", nonempty=True)
        choices(attempt["result"], RESULTS, "attempt.result")


def validate_resolution(value, stored=False):
    required = {"mode", "issue_id", "evidence"} | ({"request_id", "decided_at"} if stored else set())
    fields(value, required, "resolution", required)
    choices(value["mode"], RESOLUTION_MODES, "resolution.mode")
    string(value["issue_id"], "resolution.issue_id", nullable=value["mode"] == "continue", nonempty=True)
    if value["mode"] == "continue" and value["issue_id"] is not None:
        fail("continue 不能伪装成问题返工；issue_id 必须为 null")
    strings(value["evidence"], "resolution.evidence")
    if not value["evidence"]:
        fail("恢复决定必须附诊断、修改或验收证据")
    if stored:
        string(value["request_id"], "resolution.request_id", nonempty=True)
        timestamp(value["decided_at"], "resolution.decided_at")


def validate_worker(value, stored=False):
    allowed = WORKER_FIELDS | ({"updated_at", "last_progress_at", "last_progress", "repair_round", "applied_request_ids"} if stored else {"progress", "todos"})
    fields(value, allowed, "worker", allowed if stored else ())
    for key, item in value.items():
        if key == "state":
            choices(item, WORKER_STATES, "worker.state")
        elif key in {"phase", "summary", "progress", "last_progress"}:
            string(item, f"worker.{key}", nullable=key == "last_progress")
        elif key in {"expected_until", "updated_at", "last_progress_at"}:
            timestamp(item, f"worker.{key}", nullable=key != "updated_at")
        elif key == "evidence":
            strings(item, "worker.evidence")
        elif key == "jobs":
            validate_jobs(item)
        elif key == "writes_paused":
            boolean(item, "worker.writes_paused")
        elif key == "blocker":
            validate_blocker(item)
        elif key == "last_applied_request_id":
            string(item, "worker.last_applied_request_id", nullable=True, nonempty=True)
        elif key == "applied_request_ids":
            strings(item, "worker.applied_request_ids")
            if len(set(item)) != len(item):
                fail("worker.applied_request_ids 不得重复")
        elif key == "repair_round" and item is not None:
            required = {"issue_id", "request_id", "decision_applied_at", "attempts_baseline_count"}
            fields(item, required, "worker.repair_round", required)
            string(item["issue_id"], "repair_round.issue_id", nonempty=True)
            string(item["request_id"], "repair_round.request_id", nonempty=True)
            timestamp(item["decision_applied_at"], "repair_round.decision_applied_at")
            if type(item["attempts_baseline_count"]) is not int or item["attempts_baseline_count"] < 0:
                fail("repair_round.attempts_baseline_count 必须是非负整数")
    if stored and ((value["last_progress"] is None) != (value["last_progress_at"] is None)):
        fail("worker 的 last_progress 与 last_progress_at 必须同时存在或同时为空")
    if stored and value["last_progress"] is not None:
        string(value["last_progress"], "worker.last_progress", nonempty=True)
    if stored:
        if value["state"] == "ready_for_review" and not value["writes_paused"]:
            fail("ready_for_review 必须声明 writes_paused=true；仍需主代理核实后台写入")
        applied = value["applied_request_ids"]
        last_id = value["last_applied_request_id"]
        if last_id != (applied[-1] if applied else None):
            fail("last_applied_request_id 与已消费指导记录不一致")
        repair = value["repair_round"]
        if repair is not None:
            blocker = value["blocker"]
            if blocker is None or repair["issue_id"] != blocker["issue_id"]:
                fail("repair_round 必须对应当前 blocker 的 issue_id")
            if repair["request_id"] not in applied or repair["attempts_baseline_count"] > len(blocker["attempts"]):
                fail("repair_round 的指导身份或修复基线无效")


def validate_parent(value, stored=False, event_driven=False):
    allowed = PARENT_FIELDS | ({"updated_at", "last_checked_at", "next_check_at"} if stored else {"parent_thread_id", "worker_thread_id", "check_completed", "resume_worker", "todos", "recovery", "yield_parent", "resolution"})
    fields(value, allowed, "parent", allowed if stored else ())
    for key, item in value.items():
        if key == "state":
            choices(item, PARENT_STATES, "parent.state")
        elif key in {"check_completed", "resume_worker", "yield_parent"}:
            boolean(item, f"parent.{key}")
        elif key in {"todos", "recovery"}:
            continue  # 在取得同一把状态锁后，连同身份与依赖一起校验。
        elif key == "resolution":
            validate_resolution(item)
        elif key in {"updated_at", "last_checked_at", "next_check_at"}:
            timestamp(item, f"parent.{key}", nullable=key != "updated_at")
        else:
            string(item, f"parent.{key}", nullable=True, nonempty=key.endswith("_id"))
    if stored and not event_driven and value["state"] not in TERMINAL and value["next_check_at"] is None:
        fail("非终态必须保留 next_check_at")


def default_workflow(mode):
    choices(mode, {"standard", "goal"}, "mode")
    definitions = [("plan", "确认批准计划与分工", "parent", []),
                   ("execute", "实现、自测并提交证据", "worker", ["plan"]),
                   ("review", "主任务独立验收", "parent", ["execute"]),
                   ("close", "核实退出、清理唤醒并交付", "parent", ["review"])]
    return {"mode": mode, "todos": {
        key: {"title": title, "owner": owner, "status": "todo", "depends_on": dependencies,
              "evidence": [], "next_action": title, "waiting_for": None}
        for key, title, owner, dependencies in definitions},
        "recovery": {"kind": "unarmed", "reference": None, "check_at": None, "evidence": []},
        "resolution_history": []}


def validate_workflow(state):
    workflow = state["workflow"]
    fields(workflow, {"mode", "todos", "recovery", "resolution_history"}, "workflow", {"mode", "todos", "recovery"})
    choices(workflow["mode"], {"standard", "goal"}, "workflow.mode")
    todos = workflow["todos"]
    if not isinstance(todos, dict) or not todos:
        fail("todos 必须是非空的稳定条目 ID 映射")
    for key, item in todos.items():
        string(key, "todo ID", nonempty=True)
        required = {"title", "owner", "status", "depends_on", "evidence", "next_action", "waiting_for"}
        fields(item, required, f"todo.{key}", required)
        string(item["title"], "todo.title", nonempty=True)
        choices(item["owner"], {"parent", "worker"}, "todo.owner")
        choices(item["status"], {"todo", "running", "waiting", "blocked", "done"}, "todo.status")
        strings(item["depends_on"], "todo.depends_on")
        strings(item["evidence"], "todo.evidence")
        string(item["next_action"], "todo.next_action", nonempty=item["status"] != "done")
        string(item["waiting_for"], "todo.waiting_for", nullable=item["status"] not in {"waiting", "blocked"}, nonempty=True)
        if item["status"] == "done" and not item["evidence"]:
            fail(f"完成条目 {key} 必须提供实际证据")
        dependencies = item["depends_on"]
        if len(set(dependencies)) != len(dependencies) or any(dep not in todos or dep == key for dep in dependencies):
            fail(f"条目 {key} 存在重复、缺失或自指依赖")
    for key, item in todos.items():
        if item["status"] in {"running", "done"} and any(todos[dep]["status"] != "done" for dep in item["depends_on"]):
            fail(f"条目 {key} 的前置项未完成；变更时先重新打开受影响的验收项")
    visited, active = set(), set()

    def visit(key):
        if key in active:
            fail("todo 依赖不能成环")
        if key not in visited:
            active.add(key)
            for dep in todos[key]["depends_on"]:
                visit(dep)
            active.remove(key)
            visited.add(key)

    for key in todos:
        visit(key)
    recovery = workflow["recovery"]
    fields(recovery, {"kind", "reference", "check_at", "evidence"}, "recovery", {"kind", "reference", "check_at", "evidence"})
    choices(recovery["kind"], {"unarmed", "parent_wait", "heartbeat", "user"}, "recovery.kind")
    string(recovery["reference"], "recovery.reference", nullable=recovery["kind"] == "unarmed", nonempty=True)
    timestamp(recovery["check_at"], "recovery.check_at", nullable=recovery["kind"] in {"unarmed", "user"})
    strings(recovery["evidence"], "recovery.evidence")
    if recovery["kind"] != "unarmed" and not recovery["evidence"]:
        fail("恢复安排必须附实际工具/用户回执，不能只写计划")
    if recovery["kind"] in {"unarmed", "user"} and recovery["check_at"] is not None:
        fail("无自动恢复或等待用户时不能伪造检查期限")
    if recovery["kind"] == "heartbeat" and recovery["reference"] != state["parent"]["automation_id"]:
        fail("heartbeat 恢复安排必须匹配本轮已登记的自动化 ID")
    if recovery["kind"] == "parent_wait" and recovery["reference"] != state["identity"]["worker_thread_id"]:
        fail("parent_wait 必须等待已绑定的真实执行任务")
    if recovery["kind"] == "user" and state["parent"]["state"] != "awaiting_user":
        fail("用户恢复仅适用于真实等待用户的状态")
    if state["parent"]["next_check_at"] != recovery["check_at"]:
        fail("检查期限必须与当前恢复安排一致")
    if "resolution_history" in workflow:
        history = workflow["resolution_history"]
        if not isinstance(history, list):
            fail("resolution_history 必须是对象列表")
        seen = set()
        for resolution in history:
            validate_resolution(resolution, stored=True)
            if resolution["request_id"] in seen:
                fail("resolution_history 的 request_id 不得重复")
            seen.add(resolution["request_id"])


def applied_resolutions(state, issue_id=None):
    history = state.get("workflow", {}).get("resolution_history", [])
    applied = set(state["worker"]["applied_request_ids"])
    return [item for item in history if item["request_id"] in applied
            and (issue_id is None or item["issue_id"] == issue_id)]


def issue_requires_takeover(state, blocker):
    if blocker is None or blocker.get("kind") != "repair":
        return False
    return any(item["mode"] in {"worker_retry", "parent_takeover"}
               for item in applied_resolutions(state, blocker["issue_id"]))


def pending_resolution(state):
    if "resolution_history" not in state.get("workflow", {}):
        return None
    request_id = state["parent"]["request_id"]
    if request_id is None or request_id in state["worker"]["applied_request_ids"]:
        return None
    return next((item for item in reversed(state["workflow"]["resolution_history"])
                 if item["request_id"] == request_id), None)


def ready_parent_todos(state):
    todos = state["workflow"]["todos"]
    return [key for key, item in todos.items() if item["owner"] == "parent"
            and item["status"] in {"todo", "running"}
            and all(todos[dep]["status"] == "done" for dep in item["depends_on"])]


def update_todos(state, patch, actor):
    if not isinstance(patch, dict) or "workflow" not in state:
        fail("todos 更新需要本轮已有 workflow；不能静默迁移旧运行")
    current = state["workflow"]["todos"]
    for key, item in patch.items():
        if not isinstance(item, dict):
            fail("todo 更新必须给出完整条目，不得删除历史")
        if actor == "worker" and (key not in current or current[key]["owner"] != "worker" or item.get("owner") != "worker"):
            fail("worker 只能更新主任务已分配给自己的条目")
        if key in current and item.get("owner") != current[key]["owner"]:
            fail("已有条目负责人不能静默改变")
        current[key] = item


def validate_state(state):
    top = {"version", "run_id", "created_at", "policy", "identity", "worker", "parent"}
    fields(state, top | {"workflow"}, "state", top)
    if type(state["version"]) is not int or state["version"] != 1:
        fail("state.version 不支持；不能静默重建状态")
    string(state["run_id"], "run_id", nonempty=True)
    try:
        uuid.UUID(state["run_id"])
    except ValueError:
        fail("run_id 必须是 UUID")
    timestamp(state["created_at"], "created_at")
    policy = state["policy"]
    keys = {"check_minutes", "stalled_minutes", "repair_minutes", "max_repair_attempts"}
    fields(policy, keys, "policy", keys)
    for key in keys:
        positive(policy[key], f"policy.{key}", integer=key == "max_repair_attempts")
    identity = state["identity"]
    keys = {"parent_thread_id", "worker_target", "worker_thread_id", "objective"}
    fields(identity, keys, "identity", keys)
    for key in keys:
        string(identity[key], f"identity.{key}", nullable=key in {"parent_thread_id", "worker_thread_id"}, nonempty=True)
    validate_worker(state["worker"], stored=True)
    validate_parent(state["parent"], stored=True, event_driven="workflow" in state)
    if "workflow" in state:
        validate_workflow(state)
        if "resolution_history" in state["workflow"] and state["worker"]["blocker"] is not None:
            if "kind" not in state["worker"]["blocker"]:
                fail("新运行的 blocker 必须标明 kind=repair 或 decision")
    return state


def reject_constant(value):
    fail(f"非法 JSON 常量：{value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail(f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def read_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            return json.load(stream, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except StateError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        fail(f"JSON 无效：{path}")
    except OSError as exc:
        fail(f"无法读取 {path}：{exc.strerror}")


@contextlib.contextmanager
def locked(run_dir, create=False, readonly=False):
    folder = Path(run_dir)
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    if not folder.is_dir():
        fail(f"执行目录不存在：{folder}")
    lock_path = folder / ".state.lock"
    try:
        # check 使用已有锁文件，既不创建文件也不改写 state.json。
        with lock_path.open("a+b" if create else "rb") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH if readonly else fcntl.LOCK_EX)
            try:
                yield folder / "state.json"
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except FileNotFoundError:
        fail(f"执行记录未初始化或锁文件缺失：{folder}")


def atomic_write(path, state):
    validate_state(state)
    name = None
    try:
        fd, name = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        name = None
        # 同步目录项；原子替换确保旁路读者也不会读到半份 JSON。
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if name is not None:
            os.unlink(name)


def load_state(path):
    try:
        return validate_state(read_json(path))
    except StateError as exc:
        fail(f"执行状态不可用，未重建：{exc}")


def init_run(run_dir, *, worker_target, objective, parent_thread_id=None,
             check_minutes=30, stalled_minutes=30, repair_minutes=15,
             max_repair_attempts=2, mode=None, now=None):
    moment = now_utc(now)
    policy = dict(check_minutes=check_minutes, stalled_minutes=stalled_minutes,
                  repair_minutes=repair_minutes, max_repair_attempts=max_repair_attempts)
    for key, value in policy.items():
        positive(value, f"policy.{key}", integer=key == "max_repair_attempts")
    try:
        next_check = moment + dt.timedelta(minutes=check_minutes)
    except OverflowError:
        fail("check_minutes 超出可表示的日期范围")
    state = {
        "version": 1, "run_id": str(uuid.uuid4()), "created_at": iso(moment), "policy": policy,
        "identity": {"parent_thread_id": parent_thread_id, "worker_target": worker_target,
                     "worker_thread_id": None, "objective": objective},
        "worker": {"state": "starting", "phase": "", "summary": "", "evidence": [], "jobs": [],
                   "expected_until": None, "writes_paused": False, "blocker": None,
                   "updated_at": iso(moment), "last_progress_at": None, "last_progress": None,
                   "last_applied_request_id": None, "applied_request_ids": [], "repair_round": None},
        "parent": {"state": "watching", "decision": None, "request_id": None, "automation_id": None,
                   "updated_at": iso(moment), "last_checked_at": None, "next_check_at": iso(next_check)},
    }
    if mode is not None:
        state["workflow"] = default_workflow(mode)
        state["parent"]["next_check_at"] = None
    validate_state(state)
    with locked(run_dir, create=True) as path:
        if path.exists() or path.is_symlink():
            fail("此执行目录已有 state.json；拒绝覆盖或重新初始化")
        atomic_write(path, state)
    return state


def update_worker(run_dir, patch, *, now=None):
    validate_worker(patch)
    moment = now_utc(now)
    with locked(run_dir) as path:
        state = load_state(path)
        if state["parent"]["state"] in TERMINAL:
            fail("执行已进入终态；拒绝迟到的 worker 更新")
        worker, parent = state["worker"], state["parent"]
        old_state, old_paused = worker["state"], worker["writes_paused"]
        next_state = patch.get("state", old_state)
        next_paused = patch.get("writes_paused", old_paused)
        resumes_execution = (old_state == "needs_parent" and next_state != "needs_parent") or (
            old_paused and next_state != old_state and next_state in {"starting", "running", "waiting_external"})
        if parent["state"] in {"helping", "awaiting_user"} and (
                resumes_execution or (old_paused and not next_paused)):
            fail("主代理正在帮助或等待用户；拒绝从暂停态恢复执行或写入，可继续更新现场证据和后台任务状态")
        old_blocker = worker["blocker"]
        blocker = patch.get("blocker", old_blocker)
        guidance_blocker = blocker if blocker is not None else old_blocker
        if old_state == "ready_for_review" and (
                next_state in {"starting", "running", "waiting_external"} or not next_paused):
            if not patch.get("last_applied_request_id"):
                fail("从 ready_for_review 恢复执行需要消费本轮主代理验收指导")
        if old_state == "needs_parent" and (next_state != "needs_parent" or (old_paused and not next_paused)):
            if next_state == "starting":
                fail("needs_parent 不能退回 starting；请消费对应指导后恢复执行")
            request_id = guidance_blocker["request_id"] if guidance_blocker else None
            applied_id = patch.get("last_applied_request_id", worker["last_applied_request_id"])
            if (not guidance_blocker or request_id != applied_id or parent["request_id"] != request_id
                    or parent["state"] != "watching" or not (parent["decision"] or "").strip()
                    or (old_blocker is not None and (old_blocker["issue_id"] != guidance_blocker["issue_id"]
                                                    or old_blocker["request_id"] != request_id))):
                fail("从 needs_parent 恢复需要匹配当前求助与主代理 decision/request_id，并合法消费该轮指导")
        if old_blocker and blocker and old_blocker["issue_id"] == blocker["issue_id"]:
            if timestamp(old_blocker["first_seen_at"], "first_seen_at") != timestamp(blocker["first_seen_at"], "first_seen_at"):
                fail("同一 issue_id 的 first_seen_at 不得重置")
            attempts = old_blocker["attempts"]
            if blocker["attempts"][:len(attempts)] != attempts:
                fail("同一 issue_id 的 attempts 只能追加，不能改写或清空历史")
        elif "blocker" in patch:
            state["worker"]["repair_round"] = None
        if "last_applied_request_id" in patch:
            request_id = patch["last_applied_request_id"]
            if request_id is None:
                if state["worker"]["last_applied_request_id"] is not None:
                    fail("已消费指导的 last_applied_request_id 不得清空")
            else:
                if request_id in state["worker"]["applied_request_ids"]:
                    fail("此 request_id 的指导已消费；拒绝重复应用旧恢复消息")
                parent = state["parent"]
                matches_request = (guidance_blocker["request_id"] == request_id if guidance_blocker
                                   else old_state == "ready_for_review")
                if (not matches_request or parent["request_id"] != request_id
                        or parent["state"] != "watching" or not (parent["decision"] or "").strip()):
                    fail("应用指导需要匹配当前求助或验收与 parent 的 request_id、非空 decision，以及 parent.state=watching")
                state["worker"]["applied_request_ids"].append(request_id)
                resolution = next((item for item in reversed(state.get("workflow", {}).get("resolution_history", []))
                                   if item["request_id"] == request_id), None)
                state["worker"]["repair_round"] = {
                    "issue_id": blocker["issue_id"], "request_id": request_id,
                    "decision_applied_at": iso(moment), "attempts_baseline_count": len(blocker["attempts"]),
                } if blocker is not None and (resolution is None or resolution["mode"] == "worker_retry") else None
        if "todos" in patch:
            update_todos(state, patch["todos"], "worker")
        state["worker"].update({key: value for key, value in patch.items() if key in WORKER_FIELDS})
        state["worker"]["updated_at"] = iso(moment)
        progress = patch.get("progress", "").strip()
        if progress:
            state["worker"]["last_progress"] = progress
            state["worker"]["last_progress_at"] = iso(moment)
        atomic_write(path, state)
    return state


def update_parent(run_dir, patch, *, now=None):
    validate_parent(patch)
    moment = now_utc(now)
    with locked(run_dir) as path:
        state = load_state(path)
        if state["parent"]["state"] in TERMINAL and patch != {"automation_id": None}:
            fail("执行已进入终态；拒绝后续 parent 更新")
        if "workflow" not in state and any(key in patch for key in ("todos", "recovery", "yield_parent")):
            fail("旧运行没有 workflow；不自动改变已有运行模式")
        if "resolution" in patch and not patch.get("resume_worker", False):
            fail("resolution 只能随 resume_worker 原子记录")
        if patch.get("resume_worker", False):
            string(patch.get("request_id"), "恢复指导的 request_id", nonempty=True)
            string(patch.get("decision"), "恢复指导的 decision", nonempty=True)
            if patch.get("state", "watching") != "watching" or patch.get("check_completed", True) is False:
                fail("resume_worker 必须释放为 watching 并更新检查时间，不能同时保留帮助锁或结束运行")
            worker = state["worker"]
            blocker = worker["blocker"]
            if worker["state"] == "needs_parent" and (not blocker or blocker["request_id"] != patch["request_id"]):
                fail("恢复指导必须匹配 worker 当前求助 request_id")
            if patch["request_id"] in worker["applied_request_ids"]:
                fail("该指导已被 worker 消费；不要重复派发，请核对当前状态")
            if "resolution_history" in state.get("workflow", {}):
                resolution = patch.get("resolution")
                if resolution is None:
                    fail("新运行恢复 worker 必须声明 continue、worker_retry 或 parent_takeover")
                if worker["state"] not in {"needs_parent", "ready_for_review"}:
                    fail("只有待主任务处理或待验收状态可以记录恢复决定")
                blocker = worker["blocker"]
                if worker["state"] == "needs_parent":
                    if blocker["kind"] == "repair":
                        if resolution["mode"] == "continue" or resolution["issue_id"] != blocker["issue_id"]:
                            fail("技术问题必须匹配 issue_id，并选择 worker_retry 或 parent_takeover")
                    elif resolution["mode"] != "continue":
                        fail("协议/审批决定应使用 continue，不计作技术返工")
                if resolution["mode"] == "worker_retry" and issue_requires_takeover(state, {"kind": "repair", "issue_id": resolution["issue_id"]}):
                    fail("同一问题的 执行会话 返工额度已用完；必须由主任务接管修改")
                if resolution["mode"] == "parent_takeover":
                    if state["parent"]["state"] != "helping":
                        fail("parent_takeover 必须先进入 helping、核实 执行会话 暂停并由主任务完成修改与验证")
                    if not worker["writes_paused"]:
                        fail("parent_takeover 必须先取得 执行会话 的 writes_paused=true 暂停证据")
                if any(item["request_id"] == patch["request_id"] for item in state["workflow"]["resolution_history"]):
                    fail("该 request_id 已记录恢复决定；发送不确定时应核实原消息，不重复写决定")
                state["workflow"]["resolution_history"].append({**resolution,
                    "request_id": patch["request_id"], "decided_at": iso(moment)})
            # 同一次原子更新保存指导并释放帮助锁，成功后才能发送协作消息。
            patch = {**patch, "state": "watching", "check_completed": True}
        for key in ("parent_thread_id", "worker_thread_id"):
            if key in patch:
                previous = state["identity"][key]
                if previous is not None and previous != patch[key]:
                    fail(f"{key} 已绑定；拒绝更换或清空身份")
                state["identity"][key] = patch[key]
        state["parent"].update({key: value for key, value in patch.items() if key in PARENT_FIELDS})
        state["parent"]["updated_at"] = iso(moment)
        if "todos" in patch:
            update_todos(state, patch["todos"], "parent")
        if "recovery" in patch:
            state["workflow"]["recovery"] = patch["recovery"]
            if not isinstance(patch["recovery"], dict):
                fail("recovery 必须是对象")
            state["parent"]["next_check_at"] = patch["recovery"].get("check_at")
        if "workflow" in state and state["parent"]["state"] == "accepted":
            if any(item["status"] != "done" for item in state["workflow"]["todos"].values()):
                fail("仍有未完成待办，不能记录 accepted")
            if (not state["worker"]["writes_paused"] or state["worker"]["blocker"] is not None
                    or any(job["status"] not in {"stopped", "completed"} for job in state["worker"]["jobs"])):
                fail("退出前必须核实暂停写入、阻塞已处理且本轮作业已结案")
        if "workflow" in state and state["parent"]["state"] == "cancelled":
            if (not state["worker"]["writes_paused"]
                    or any(job["status"] not in {"stopped", "completed"} for job in state["worker"]["jobs"])):
                fail("取消前必须暂停写入并确认作业退出；未确认时保留活动状态继续清理")
        if state["parent"]["state"] in TERMINAL:
            state["parent"]["next_check_at"] = None
            if "workflow" in state:
                state["workflow"]["recovery"] = default_workflow("standard")["recovery"]
            if patch.get("check_completed", False):
                state["parent"]["last_checked_at"] = iso(moment)
        elif patch.get("check_completed", False):
            state["parent"]["last_checked_at"] = iso(moment)
            if "workflow" not in state:
                try:
                    next_check = moment + dt.timedelta(minutes=state["policy"]["check_minutes"])
                except OverflowError:
                    fail("check_minutes 超出可表示的日期范围")
                state["parent"]["next_check_at"] = iso(next_check)
        validate_state(state)
        if patch.get("yield_parent"):
            action, _ = choose_action(state, moment, due=False, force=False)
            if action in {"help", "takeover", "review", "parent_helping"}:
                fail("仍有待处理求助、验收或主任务介入；先处理交接，不能等待心跳")
            if ready_parent_todos(state) and state["parent"]["state"] != "awaiting_user":
                fail("主任务仍有可执行待办；先完成或明确记录等待原因")
            recovery = state["workflow"]["recovery"]
            if recovery["kind"] not in {"heartbeat", "user"}:
                fail("主任务结束等待前必须有已落实的心跳或真实用户恢复；正在 wait 不能保证空闲后唤醒")
            if recovery["kind"] == "heartbeat" and timestamp(recovery["check_at"], "check_at") <= moment:
                fail("恢复期限已经到达，应先检查而非结束轮次")
        atomic_write(path, state)
    return state


def choose_action(state, moment, due, force):
    parent, worker, policy = state["parent"], state["worker"], state["policy"]
    if parent["state"] in TERMINAL:
        return "closed", "执行已验收或取消；不再续跑"
    if parent["state"] == "awaiting_user":
        return "await_user", "等待用户决策或授权；不得自动续跑"
    if parent["state"] == "helping":
        return "parent_helping", "主代理正在介入；按接管约定协调写入"
    if worker["state"] == "needs_parent":
        if pending_resolution(state) is not None:
            return "await_worker_resume", "主任务已记录恢复决定；等待 执行会话 消费，不重复派发"
        if issue_requires_takeover(state, worker["blocker"]):
            return "takeover", "同一技术问题已用过一次 执行会话 返工或已由主任务接管；主任务继续修改"
        return "help", "执行会话 已请求主代理帮助"
    if worker["state"] == "ready_for_review":
        if pending_resolution(state) is not None:
            return "await_worker_resume", "主任务已记录恢复决定；等待 执行会话 消费，不重复派发"
        return "review", "执行会话 已提交实现；需要主代理独立验收"
    blocker = worker["blocker"]
    if blocker is not None:
        repair = worker["repair_round"]
        start_at = timestamp(repair["decision_applied_at"] if repair else blocker["first_seen_at"], "repair_started_at")
        attempts = blocker["attempts"][repair["attempts_baseline_count"]:] if repair else blocker["attempts"]
        failed_methods = {a["method"].strip().casefold() for a in attempts if a["result"] == "failed"}
        if len(failed_methods) >= policy["max_repair_attempts"]:
            return ("takeover", "同一技术问题的 执行会话 返工已失败；主任务接管修改") if issue_requires_takeover(state, blocker) else ("help", "同一问题已达到不同修复方法失败次数阈值")
        if moment - start_at >= dt.timedelta(minutes=policy["repair_minutes"]):
            return ("takeover", "同一技术问题的 执行会话 返工已超时；主任务接管修改") if issue_requires_takeover(state, blocker) else ("help", "同一问题排障时间已达到阈值，需要主代理诊断")
    if "workflow" in state:
        if ready_parent_todos(state):
            return "continue_parent", "主任务仍有可执行待办，不应提前结束"
        if state["workflow"]["recovery"]["kind"] == "unarmed":
            return "arrange_recovery", "尚无实际恢复安排；清单本身不会唤醒模型"
    if not due and not force:
        return "not_due", "尚未到定时检查时间，且未收到需立即介入的状态"
    if worker["state"] == "waiting_external":
        expected = timestamp(worker["expected_until"], "expected_until", nullable=True)
        if expected is not None and expected > moment and worker["evidence"]:
            return "continue", "外部任务有进度证据且尚未到预计时间；可轻量核对任务身份后继续等待"
        if expected is not None and expected <= moment:
            return "investigate", "外部任务已到预计时间；核查任务实际状态，不自动终止或重启"
        return "investigate", "外部等待缺少预计时间或进度证据；需要核查"
    if worker["state"] == "starting" or not worker["summary"].strip():
        return "request_status", "尚缺少执行阶段或有效状态摘要；向同一个 执行会话 获取一次状态"
    threshold = dt.timedelta(minutes=policy["stalled_minutes"])
    if moment - timestamp(worker["updated_at"], "updated_at") >= threshold:
        return "request_status", "状态记录已过期；核查同一个 执行会话 的当前状态"
    progress_at = timestamp(worker["last_progress_at"] or state["created_at"], "last_progress_at")
    if moment - progress_at >= threshold:
        return "request_status", "实质进展已超过检查阈值；获取一次状态，不将普通刷新视为进展"
    return "continue", "近期有实质进展；继续执行"


def check_run(run_dir, *, force=False, compact=False, now=None):
    boolean(force, "force")
    boolean(compact, "compact")
    moment = now_utc(now)
    with locked(run_dir, readonly=True) as path:
        state = load_state(path)
    # 旧版终态也可能留有截止时间；不能据此继续安排检查。
    terminal = state["parent"]["state"] in TERMINAL
    deadline = timestamp(state["parent"]["next_check_at"], "next_check_at", nullable=True)
    due = not terminal and deadline is not None and moment >= deadline
    action, reason = choose_action(state, moment, due, force)
    worker, parent = state["worker"], state["parent"]
    result = {
        "run_id": state["run_id"], **state["identity"], "due": due, "forced": force,
        "action": action, "reason": reason, "checked_at": iso(moment), "created_at": state["created_at"],
        "worker_state": worker["state"], "parent_state": parent["state"], "phase": worker["phase"],
        "summary": worker["summary"], "updated_at": worker["updated_at"],
        "last_progress_at": worker["last_progress_at"], "last_progress": worker["last_progress"],
        "last_checked_at": parent["last_checked_at"], "next_check_at": None if terminal else parent["next_check_at"],
        "automation_id": parent["automation_id"],
        "expected_until": worker["expected_until"], "writes_paused": worker["writes_paused"],
        "evidence": worker["evidence"], "jobs": worker["jobs"], "blocker": worker["blocker"],
        "last_applied_request_id": worker["last_applied_request_id"], "repair_round": worker["repair_round"],
    }
    if "workflow" in state:
        result.update(mode=state["workflow"]["mode"], recovery=state["workflow"]["recovery"],
                      pending_todos=[key for key, item in state["workflow"]["todos"].items() if item["status"] != "done"],
                      ready_parent_todos=ready_parent_todos(state))
        if "resolution_history" in state["workflow"]:
            result["resolution_history"] = state["workflow"]["resolution_history"]
    if compact:
        for key in ("worker_target", "objective", "created_at", "last_progress", "last_checked_at", "resolution_history"):
            result.pop(key, None)
        result.update(state_path=str(path.resolve()), request_id=parent["request_id"],
                      decision=parent["decision"], pending_resolution=pending_resolution(state))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="新建执行记录；拒绝覆盖已有状态")
    init.add_argument("--parent-thread-id", help="已确认的主任务 ID；未知时省略")
    init.add_argument("--worker-target", required=True, help="本轮稳定逻辑标识，例如 executor-session:run")
    init.add_argument("--objective", required=True, help="本次执行目标")
    init.add_argument("--mode", choices=("standard", "goal"), default="standard", help="新运行默认普通模式；goal 必须传递本轮明确授权")
    init.add_argument("--check-minutes", type=float, default=30, help="仅供无 workflow 的旧记录兼容；新运行按 recovery.check_at 安排")
    init.add_argument("--stalled-minutes", type=float, default=30)
    init.add_argument("--repair-minutes", type=float, default=15)
    init.add_argument("--max-repair-attempts", type=int, default=2)
    worker = sub.add_parser("worker", help="更新 worker 状态；只有非空 progress 表示实质进展")
    worker.add_argument("--input", required=True, help="UTF-8 JSON 更新文件")
    parent = sub.add_parser("parent", help="更新主代理状态；resume_worker=true 须带修复路由并原子释放帮助锁")
    parent.add_argument("--input", required=True, help="UTF-8 JSON 更新文件")
    check = sub.add_parser("check", help="只读返回处理建议，不移动检查时间")
    check.add_argument("--force", action="store_true", help="忽略检查时间门槛；仍尊重人工等待和终态")
    check.add_argument("--compact", action="store_true", help="省去重复目标与历史；保留当前处理依据和完整状态路径")
    for command in (init, worker, parent, check):
        command.add_argument("--run-dir", required=True, help="本次执行专用目录")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        if command == "init":
            result = init_run(**args)
        elif command == "check":
            result = check_run(**args)
        else:
            patch = read_json(args.pop("input"))
            result = (update_worker if command == "worker" else update_parent)(patch=patch, **args)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        return 0
    except (StateError, OSError) as exc:
        message = str(exc) if isinstance(exc, StateError) else (exc.strerror or str(exc))
        print(f"错误：{message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
