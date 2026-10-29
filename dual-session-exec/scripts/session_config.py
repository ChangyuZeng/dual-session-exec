#!/usr/bin/env python3
"""记录两侧独立模型选择；不切换模型、不启动或发送会话。Python 3.11+。"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")
    return value


def setting(value):
    if value is None or value == "inherit":
        return None
    text(value, "配置")
    if value == "unsupported":
        raise ValueError("unsupported 是能力说明，不能作为模型或思考强度")
    return value


def role_settings(model, thinking, source):
    return {"requested_model": setting(model), "requested_thinking": setting(thinking),
            "selection_source": text(source, "source"), "config_revision": 1,
            "runtime_confirmation": None}


def create_session(run_id, adapter, source, parent_model=None, parent_thinking=None,
                   worker_model=None, worker_thinking=None):
    if adapter not in {"native", "subagent", "manual", "codex"}:
        raise ValueError("未知 adapter")
    return {"session_version": 2, "run_id": text(run_id, "run_id"), "adapter": adapter,
            "creation_status": "prepared", "parent_thread_id": None, "parent_host_id": None,
            "worker_thread_id": None, "worker_host_id": None, "client_thread_id": None,
            "worker_cwd": None, "role_model_settings": {
                "parent": role_settings(parent_model, parent_thinking, source),
                "worker": role_settings(worker_model, worker_thinking, source)}}


def select(session, role, updates, source):
    if session.get("session_version") != 2:
        raise ValueError("只更新 v2 session；旧运行不自动迁移")
    if role not in {"parent", "worker"} or not updates:
        raise ValueError("须指定 parent/worker 及至少一个配置项")
    if set(updates) - {"requested_model", "requested_thinking"}:
        raise ValueError("只允许更新模型和思考强度")
    result = json.loads(json.dumps(session, ensure_ascii=False, allow_nan=False))
    target = result["role_model_settings"][role]
    for name, value in updates.items():
        target[name] = setting(value)
    revision = target["config_revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("无效的配置版本")
    target.update(selection_source=text(source, "source"), config_revision=revision + 1,
                  runtime_confirmation=None)
    return result


def save(path, value, new=False):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if new:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="新建配置记录，不覆盖已有文件")
    init.add_argument("--out", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--adapter", choices=("native", "subagent", "manual", "codex"), required=True)
    init.add_argument("--source", required=True)
    for role in ("parent", "worker"):
        init.add_argument(f"--{role}-model")
        init.add_argument(f"--{role}-thinking")
    change = commands.add_parser("select", help="记录一侧最新选择，清空其旧运行确认")
    change.add_argument("--session", required=True)
    change.add_argument("--role", choices=("parent", "worker"), required=True)
    change.add_argument("--model", default=argparse.SUPPRESS)
    change.add_argument("--thinking", default=argparse.SUPPRESS)
    change.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "init":
            result = create_session(args.run_id, args.adapter, args.source, args.parent_model,
                                    args.parent_thinking, args.worker_model, args.worker_thinking)
            path = args.out
        else:
            result = json.loads(Path(args.session).read_text(encoding="utf-8"))
            updates = {f"requested_{name}": getattr(args, name) for name in ("model", "thinking")
                       if hasattr(args, name)}
            result = select(result, args.role, updates, args.source)
            path = args.session
        save(path, result, new=args.action == "init")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"配置记录失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({"saved": path, "runtime_applied": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
