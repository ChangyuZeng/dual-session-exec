#!/usr/bin/env python3
"""按获批时间额度运行一个前台本地作业，处理中断并清理自身进程组。"""

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class Interrupted(Exception):
    def __init__(self, signum):
        self.signum = signum


def positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("必须是有限正数")
    return value


def grant_seconds(max_seconds, gpu_count, remaining_gpu_hours):
    if type(gpu_count) is not int or gpu_count < 0:
        raise ValueError("gpu_count 必须是非负整数")
    cap = positive(max_seconds)
    if gpu_count:
        if remaining_gpu_hours is None:
            raise ValueError("GPU 作业必须提供已经为本作业预留的剩余 GPUh")
        cap = min(cap, positive(remaining_gpu_hours) * 3600 / gpu_count)
    elif remaining_gpu_hours is not None:
        raise ValueError("CPU 作业不能消耗 GPU 额度")
    return cap


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # macOS 在组内进程退出/被收养期间也可能短暂返回 EPERM；不能当作已退出。
        return True


def stop_group(pgid, proc, grace):
    if not group_exists(pgid):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        pass
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        proc.poll()
        if not group_exists(pgid):
            return
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_job(command, cwd, max_seconds, gpu_count, remaining_gpu_hours, report):
    cap = grant_seconds(max_seconds, gpu_count, remaining_gpu_hours)
    if not command or not Path(cwd).is_dir():
        raise ValueError("必须提供有效 cwd 和前台命令")
    report = Path(report)
    # 在启动前验证日志可写，且不覆盖前一次作业结果。
    with report.open("x", encoding="utf-8") as result_stream:
        result = {"command": command, "cwd": str(Path(cwd).resolve()),
                  "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "limit_seconds": cap, "gpu_count": gpu_count, "status": "starting"}

        def save():
            result_stream.seek(0)
            json.dump(result, result_stream, ensure_ascii=False, indent=2)
            result_stream.write("\n")
            result_stream.truncate()
            result_stream.flush()
            os.fsync(result_stream.fileno())

        save()
        proc = None
        start = time.monotonic()
        grace = min(2.0, cap / 5)

        def interrupt(signum, frame):
            raise Interrupted(signum)

        old_handlers = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
        exit_code = 2
        try:
            proc = subprocess.Popen(command, cwd=cwd, start_new_session=True)
            result.update(status="running", pid=proc.pid, pgid=proc.pid)
            save()
            try:
                code = proc.wait(timeout=max(0, cap - grace - (time.monotonic() - start)))
                # 只支持前台作业：父进程退出但后代仍活跃也必须清理，不能报告成功。
                leftover = group_exists(proc.pid)
                result.update(status="leftover_children" if leftover else ("completed" if code == 0 else "failed"),
                              returncode=code)
                exit_code = 1 if leftover else (code if code >= 0 else 128 - code)
            except subprocess.TimeoutExpired:
                result["status"] = "budget_exhausted"
                exit_code = 124
        except Interrupted as exc:
            result.update(status="interrupted", signal=exc.signum)
            exit_code = 128 + exc.signum
        except OSError as exc:
            result.update(status="launch_failed", error=str(exc))
        finally:
            for sig in old_handlers:
                signal.signal(sig, signal.SIG_IGN)
            try:
                if proc is not None:
                    stop_group(proc.pid, proc, grace)
                    proc.wait()
                    result["process_group_gone"] = not group_exists(proc.pid)
                    if not result["process_group_gone"]:
                        result["status"] = "cleanup_unconfirmed"
                        exit_code = 2
                result["elapsed_seconds"] = time.monotonic() - start
                if gpu_count:
                    result["allocated_gpu_hours"] = result["elapsed_seconds"] * gpu_count / 3600
                save()
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
        return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--max-seconds", type=positive, required=True)
    parser.add_argument("--gpu-count", type=int, required=True)
    parser.add_argument("--remaining-gpu-hours", type=positive)
    parser.add_argument("--report", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return run_job(command, args.cwd, args.max_seconds, args.gpu_count, args.remaining_gpu_hours, args.report)
    except (OSError, ValueError, argparse.ArgumentTypeError) as exc:
        print(f"作业守护失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
