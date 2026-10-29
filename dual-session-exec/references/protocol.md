# 通用执行协议

## 契约与持久记录

`contract.md` 是批准范围、输入输出和通过标准的唯一契约。写清 run_id/版本、批准来源、双方身份、角色入口和状态目录的实际可读位置；cwd/输入与数据模型配置版本/脏改动基线/允许写入路径；稳定条目 ID/依赖/必须或已授权可选输出/验证命令与证据位置；额度/已用量与活动预留/硬退出控制/原审批点/停止与求助条件；adapter/两侧配置来源/模式/恢复办法。只填当前任务相关内容，不用占位符假装输入齐全。

契约改版只同步差异并重新打开受影响待办。复杂任务分准备、获准最小检查、正式运行、分析/验收；简单任务合并步骤，不新增未经授权的试跑或审批。完成和复用必须有匹配的输入、代码、环境、配置、标准和依赖证据。失败与负结果保留，不能更换样本、阈值或研究假设来通过。

每轮一个新目录。`session.json` 记录配置与身份，主会话单写；`state.json` 保存唯一待办、阻塞、作业和决策；证据另存，不全量塞进状态或消息。人工跨机协作把副本标成投递快照，由接收方按 run_id/版本/事件 ID 合并，不能让两份状态同时当权威。

v2 session 最小语义：

```json
{
  "session_version": 2,
  "run_id": "由本轮状态生成的唯一标识",
  "adapter": "native",
  "creation_status": "prepared",
  "parent_thread_id": null,
  "parent_host_id": null,
  "worker_thread_id": null,
  "worker_host_id": null,
  "client_thread_id": null,
  "worker_cwd": null,
  "role_model_settings": {
    "parent": {"requested_model": null, "requested_thinking": null, "selection_source": "用户本轮指令或宿主默认", "config_revision": 1, "runtime_confirmation": null},
    "worker": {"requested_model": null, "requested_thinking": null, "selection_source": "用户本轮指令或宿主默认", "config_revision": 1, "runtime_confirmation": null}
  }
}
```

上述未知身份不能用于工具调用。adapter 可为 native/subagent/manual 或具体的 codex；实际操作映射及来源记在契约。runtime_confirmation 有观察证据才填：实际 model、thinking（不可观察为 null）、turn_id、observed_at、source、对应 config_revision。只确认可观察字段，不能把局部确认称为完整匹配。选项变化后旧确认失效。

生成与修改配置（路径和型号换成用户实际选择；不想覆盖的字段省略）：

```sh
python3 <技能目录>/scripts/session_config.py init --out <本轮目录>/session.json --run-id <实际run_id> --adapter native --source <用户指令来源>
python3 <技能目录>/scripts/session_config.py select --session <本轮目录>/session.json --role worker --model <用户选择的可用模型ID> --thinking <该模型支持的值> --source <本轮修改来源>
```

select 只更新记录并清空该侧旧确认，不切换当前模型。显式 `inherit` 清除对应覆盖，不作为模型/强度传给宿主。旧 session 不自动升级。

## 可选状态助手

POSIX + Python 3.11+ 可复用本包 `scripts/supervision.py`，它只管理文件和给出下一步建议；不创建代理、管理进程、发送消息或证明收尾。只在需要时看 CLI/--help；不要先把完整实现加载到上下文。Windows 或没有运行时可按同一语义维护记录；没有文件锁时由一方串行写入，另一方只投递事件。

```sh
python3 <技能目录>/scripts/supervision.py init --mode standard --run-dir <本轮目录> --worker-target <本轮稳定逻辑标识> --parent-thread-id <实际主会话ID> --objective <批准目标>
python3 <技能目录>/scripts/supervision.py parent --run-dir <本轮目录> --input <本轮目录>/parent-update.json
python3 <技能目录>/scripts/supervision.py worker --run-dir <本轮目录> --input <本轮目录>/worker-update.json
python3 <技能目录>/scripts/supervision.py check --compact --force --run-dir <本轮目录>
```

parent 只能由主会话调用，worker 只更新执行字段及自己的既有待办；不手改 state.json。默认 plan → execute → review → close，复杂任务添加有证据依赖的条目，并让 execute 依赖最后必需步骤。每条有 title、owner、status、depends_on、evidence、next_action、waiting_for；done 必须 evidence 非空且依赖完成，waiting/blocked 必须原因与下一步。

`--input` 文件是该角色的直接更新对象，字段放在 JSON 根层；不能再包成 `{"worker": {...}}` 或 `{"parent": {...}}`，也不提交完整 state。收到开始指令后先记录 running，再实施修改。例如 worker-update.json 的最小开始更新为：

```json
{"state":"running","phase":"execute","summary":"已开始本轮批准实现","writes_paused":false}
```

完成时在同一个直接更新对象添加 `todos.execute` 的完整条目（保留 owner/title/depends_on，status=done，附 evidence，清空已完成项的 next_action/waiting_for），并设 state=ready_for_review、writes_paused=true。接口拒绝更新时保留错误，状态未保存就不能声称状态已变；修正输入后只重做该更新，不重跑已经有效的实现与自测。

worker 常用更新：`state`（starting/running/waiting_external/needs_parent/ready_for_review）、phase、summary、evidence、writes_paused、jobs。仅实质进展填 progress。job 记录 job_id/kind/pid（可空）/write_scope/status（running/stopped/completed/unknown）；真实主机与创建时间写进 job_id，PID 单独不能证明身份。

技术 blocker 字段为 kind=repair、issue_id、request_id、reason、first_seen_at（含时区）、attempts（method/result）、requested_help；决策阻塞用 kind=decision。求助与审查前暂停相关写入，仍运行后台作业照实登记。

parent 恢复输入包括 resume_worker=true、request_id、decision、resolution（mode/issue_id/evidence）；mode 为 continue/worker_retry/parent_takeover。continue 的 issue_id 必须 null；修复必须匹配原 issue。接管前 parent.state=helping，核实暂停与后台写入，完成补丁及验证后再原子保存恢复决定。执行侧通过 last_applied_request_id 消费一次。不得改名清除历史或重置返工额度。

恢复记录 recovery 使用 kind=unarmed/parent_wait/heartbeat/user，加 check_at、reference、evidence；安排理由写入契约或引用证据，不向该对象添加 reason 字段。真实恢复来源才能写 evidence。parent_wait 仅表示主会话当前活动等待。yield_parent=true 要求无未处理求助/验收/主会话可执行工作及真实恢复安排；文件时间和字段本身不安装定时器。

结束时 parent.state=accepted/cancelled。accepted 的程序守卫检查待办、暂停写入、阻塞和作业状态，但不会验证其背后的真实世界；主会话仍须核查执行者 idle、goal 与唤醒清理。历史无 workflow 记录保持原语义，不注入新模式。

## 独立验收与内容复用

主会话对稳定材料完成一次可做的完整审查：合并必修项、建议及因依赖尚不能判断的项。通过后可以使用 `scripts/review_receipt.py`：

```sh
python3 <技能目录>/scripts/review_receipt.py snapshot --manifest <条目manifest.json> --out <新快照.json>
python3 <技能目录>/scripts/review_receipt.py seal --snapshot <快照.json> --decision <主会话决定.json> --session <session.json> --out <新回执.json>
python3 <技能目录>/scripts/review_receipt.py check --manifest <条目manifest.json> --receipt <回执.json> --session <session.json>
```

manifest 仅含 run_id、item_id、criteria、context（验证命令/环境/外部依赖版本）、inputs 和 evidence（非空真实绝对路径列表）。快照及报告放在这些目录之外。decision 含 run_id、item_id、reviewer_thread_id（原主会话）、verdict=accepted、required_fixes=[]、report_path。登记完整依赖，不能以易变路径替代数据/模型版本。

check 的 exit 0 表示已登记材料/标准/报告未变，exit 1 表示变化需要相关重验，exit 2 是错误不得复用。内容指纹不是鉴权，也发现不了未登记依赖或新反证；主会话真实审查、原计划集成检查和新失败处理不能省略。

## 作业、目标与退出

作业额度与退出优先使用已有 runner/调度器，启动前核对总账、活动预留和本作业额度，未知不启动受限工作。可选 `scripts/job_guard.py --help` 提供 POSIX 本机前台进程组的时间/GPU 分配时长控制。它不能控制远端调度器、脱离进程组的 daemon、全局累计预算或主机掉线；每次退出保留真实回执，不能以本机 SSH 结束证明远端已清理。

standard 不创建目标；goal 只有本轮明确选择且宿主支持时启用。创建、恢复、关闭都核对执行侧真实目标状态。token_budget 只在用户明确给出时设置，其他预算不能臆造换算。取消、预算耗尽和未知退出不记 complete。

收尾先处理实际作业、执行会话、目标和专属唤醒，再记录终态及已确认回执。无工具能力就明确所需用户动作和未完成项。报告请求配置与观察结果分别列出，缺用量保持 unknown；状态测试、字符压缩比例或固定模型名不能证明执行质量、计费或跨宿主兼容。
