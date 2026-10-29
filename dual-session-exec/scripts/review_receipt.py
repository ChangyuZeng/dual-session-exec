#!/usr/bin/env python3
"""核对独立验收快照是否仍可复用；不执行测试，不替代主任务的判断。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(paths):
    result = {}
    for value in paths:
        root = Path(value)
        if not root.is_absolute() or root.is_symlink():
            raise ValueError(f"必须提供真实绝对路径，不接受符号链接：{root}")
        entries = [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]
        for path in entries:
            if path.is_symlink():
                raise ValueError(f"请显式登记链接目标或不可变版本：{path}")
            if path.is_file():
                result[str(path)] = digest(path)
            elif path.is_dir():
                result[str(path)] = "directory"
            else:
                raise ValueError(f"验收输入缺失或不是普通文件/目录：{path}")
    return result


def capture(manifest):
    required = {"run_id", "item_id", "criteria", "context", "inputs", "evidence"}
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError(f"manifest 必须且只能包含：{', '.join(sorted(required))}")
    for name in ("run_id", "item_id", "criteria"):
        if not isinstance(manifest[name], str) or not manifest[name].strip():
            raise ValueError(f"{name} 必须是非空字符串")
    if not isinstance(manifest["context"], dict) or not manifest["context"]:
        raise ValueError("context 必须记录验证命令、环境及外部依赖版本")
    for name in ("inputs", "evidence"):
        paths = manifest[name]
        if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p for p in paths):
            raise ValueError(f"{name} 必须是非空路径列表")
        if len(set(paths)) != len(paths):
            raise ValueError(f"{name} 不能重复")
    # JSON 副本防止调用方之后修改同一个 manifest 对象。
    frozen = json.loads(json.dumps(manifest, ensure_ascii=False, allow_nan=False))
    return {"manifest": frozen, "fingerprints": fingerprint(frozen["inputs"] + frozen["evidence"])}


def seal(snapshot, decision, session):
    manifest = snapshot["manifest"]
    if capture(manifest) != snapshot:
        raise ValueError("审查期间输入、依赖或证据已变化，不能封存旧结论")
    if (session["run_id"] != manifest["run_id"]
            or decision["run_id"] != manifest["run_id"]
            or decision["item_id"] != manifest["item_id"]
            or not session.get("parent_thread_id")
            or session.get("parent_thread_id") == session.get("worker_thread_id")
            or decision["reviewer_thread_id"] != session["parent_thread_id"]):
        raise ValueError("验收决定必须对应本轮条目及已绑定的原主任务")
    if decision.get("verdict") != "accepted" or decision.get("required_fixes") != []:
        raise ValueError("只有必修项全部解决、独立验收通过的条目可以封存")
    report = fingerprint([decision["report_path"]])
    if not Path(decision["report_path"]).is_file():
        raise ValueError("report_path 必须是主任务定稿验收报告文件")
    return {"version": 1, "snapshot": snapshot, "decision": decision, "report_fingerprint": report}


def check(manifest, receipt, session):
    if receipt.get("version") != 1:
        raise ValueError("不支持的验收回执版本")
    # 再检查身份、通过状态与报告存在性；这里只读，不改变回执。
    old = receipt["snapshot"]
    decision = receipt["decision"]
    if (decision.get("verdict") != "accepted" or decision.get("required_fixes") != []
            or decision.get("run_id") != manifest["run_id"]
            or old["manifest"]["run_id"] != manifest["run_id"]
            or decision.get("item_id") != manifest["item_id"]
            or old["manifest"]["item_id"] != manifest["item_id"]
            or session.get("run_id") != manifest["run_id"]
            or not session.get("parent_thread_id")
            or session.get("parent_thread_id") == session.get("worker_thread_id")
            or decision.get("reviewer_thread_id") != session["parent_thread_id"]):
        raise ValueError("回执不是本轮条目的有效主任务验收决定")
    current = capture(manifest)
    changed = ["manifest"] if current["manifest"] != old["manifest"] else []
    before, after = old["fingerprints"], current["fingerprints"]
    changed.extend(path for path in sorted(before.keys() | after.keys()) if before.get(path) != after.get(path))
    if fingerprint([decision["report_path"]]) != receipt["report_fingerprint"]:
        changed.append("review_report")
    return {"run_id": manifest["run_id"], "item_id": manifest["item_id"],
            "reusable": not changed, "changed": changed}


def write_new(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path)  # 已有快照/回执不能被覆盖。
        finally:
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--manifest", required=True)
    snapshot.add_argument("--out", required=True)
    accept = sub.add_parser("seal")
    for name in ("snapshot", "decision", "session", "out"):
        accept.add_argument(f"--{name}", required=True)
    reuse = sub.add_parser("check")
    for name in ("manifest", "receipt", "session"):
        reuse.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        if args.action == "snapshot":
            write_new(args.out, capture(read_json(args.manifest)))
        elif args.action == "seal":
            write_new(args.out, seal(read_json(args.snapshot), read_json(args.decision), read_json(args.session)))
        else:
            result = check(read_json(args.manifest), read_json(args.receipt), read_json(args.session))
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["reusable"] else 1
        print(json.dumps({"saved": args.out}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"reusable": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
