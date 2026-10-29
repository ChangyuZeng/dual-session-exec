#!/usr/bin/env python3
"""按接收任务生成 send_message_to_thread 参数；本脚本不发送消息。"""

import argparse
import json
from pathlib import Path
import sys


def required_text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少非空字符串：{key}")
    return value


def build_args(session, destination, prompt):
    if destination not in {"parent", "worker"}:
        raise ValueError("接收方必须是 parent 或 worker")
    version = session.get("session_version", 1)
    if type(version) is not int or version not in {1, 2}:
        raise ValueError("不支持的 session_version")
    if version == 2 and session.get("adapter") != "codex":
        raise ValueError("本助手仅生成 Codex 桌面参数，其他宿主须使用自身适配")
    parent_id = required_text(session, "parent_thread_id")
    worker_id = required_text(session, "worker_thread_id")
    if parent_id == worker_id or worker_id == session.get("client_thread_id"):
        raise ValueError("主任务和执行任务必须绑定不同的真实 threadId")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("消息不能为空")
    result = {
        "threadId": session[f"{destination}_thread_id"],
        "hostId": required_text(session, f"{destination}_host_id"),
        "prompt": prompt,
    }
    # 回报主会话不携带模型覆盖；主侧选择只由用户或宿主控制。
    if destination == "worker":
        settings = session.get("role_model_settings", {}).get("worker", {})
        for argument, key in (("model", "requested_model"), ("thinking", "requested_thinking")):
            if version == 2 and key not in settings:
                raise ValueError(f"缺少配置字段：{key}")
            if version == 2 and settings[key] is None:
                continue
            value = required_text(settings, key)
            if version == 2 and value in {"inherit", "unsupported"}:
                raise ValueError(f"{value} 不能直接传入 API")
            result[argument] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="已绑定的 session.json")
    parser.add_argument("--to", choices=("parent", "worker"), required=True)
    parser.add_argument("--prompt-file", required=True, help="UTF-8 原文消息文件")
    args = parser.parse_args(argv)
    try:
        session = json.loads(Path(args.session).read_text(encoding="utf-8"))
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        result = build_args(session, args.to, prompt)
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        print(f"参数生成失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
