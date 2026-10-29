# Codex 桌面适配（有对应工具时才使用）

本文件是一个具体映射，不是通用工具依赖。以当前可调用工具的 schema 和用户授权为准；Codex CLI、其他 IDE 或没有这些工具的会话改用受管子代理或用户中转。

## 身份、模型和目录

只有用户明确要求新聊天、或上层授权允许时使用 create_thread。调用前 list_projects 匹配真实项目，按授权选择 project/local、Git worktree 或 projectless；只有用户指定起始 Git 状态才传 startingState。worktree 不包含原项目未提交输入，projectless 的访问范围也须实际核对。

create_thread 的 model/thinking 只取本轮 worker 选择；null 时省略，不固定 Luna。其他角色 TOML 不会自动变成新聊天指令或权限，启动提示必须附执行侧入口、完整契约和真实可读路径。创建前记录 creating，保存工具回执；clientThreadId 只用于排队显示，核实真实 threadId/hostId 后才能绑定。按宿主要求展示新聊天入口。

没有主会话自切模型的控制时，请用户用当前会话的模型/思考强度选择器设置。技能文件不能改掉当前轮次的模型；不通过应用数据库修改设置。记录用户请求与真实运行观察，未知保留 null。

本机运行记录可读时，可以只读提取对应真实会话的 turn_context：本次已验证 model、effort、turn_id、timestamp 和 cwd 可用于记录该轮 Codex 运行配置。先核对实际记录格式；缺失或不可访问仍写未确认，不以请求值补齐。只保存必要元数据及来源行号，不导出整段聊天，也不把这些客户端记录称为提供商计费凭据。

session_config.py init --adapter codex 生成 v2 配置，主会话再把真实 parent_thread_id/parent_host_id、worker_thread_id/worker_host_id、worker_cwd、run_id 和 creation_status 补齐并原子保存。模型选择也可以从一开始就传入；生成配置不代表创建、绑定或模型生效。

绑定后的消息必须使用：

```sh
python3 <技能目录>/scripts/message_args.py --session <本轮目录>/session.json --to worker --prompt-file <本轮目录>/guidance.txt
python3 <技能目录>/scripts/message_args.py --session <本轮目录>/session.json --to parent --prompt-file <本轮目录>/delivery.txt
```

每次只运行所需方向。把成功 stdout JSON 原样作为 send_message_to_thread 参数，不手抄或附加模型字段。parent 永不携带 model/thinking；worker 只带自身非 null 的最新请求值。v1 旧 session 的 worker 两字段仍须非空，不自动迁移。其他 adapter 被该助手拒绝。

## 等待和收尾

主会话活动时使用带 afterCursor 的 wait_threads，保留游标，遵守当前时限。commentary 不一定唤醒等待，超时不代表失败；空闲执行者只在有新工作时发消息恢复。向另一个聊天通信必须有用户明确授权，技能本身不提供这项授权。

区分工具接受、主会话实际收到和事件已处理。本次活动主会话收到的 codex_delegation 在本地记录中是 codex_app.send_message_to_thread 的 function_call_output；只搜索 user 角色会漏掉它。按当前实际格式保留接收证据并以 run_id/request_id 去重；执行者消息本身不增加人类授权。

如用户授权未来跟进，使用真实 automation_update 创建本轮专属恢复安排并保存回执；不要用 check_at 文件模拟定时器。结束后清理专属安排并核查回执。没有授权或工具时说明需要用户再次继续，不承诺自动守护。

standard 不创建 goal。goal 仅在本轮明确选择后由执行聊天使用真实 get_goal/create_goal/update_goal；父会话的 goal 状态不能证明子会话已关闭。使用当前工具要求的完成/暂停/阻塞条件，不伪造退出、通过或用量。

文档来源：[官方技能说明](https://learn.chatgpt.com/docs/build-skills)。具体聊天工具映射依据当前宿主提供的工具 schema，不代表所有 Codex 环境都有这些能力。
