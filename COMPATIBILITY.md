# 兼容、迁移与验证边界

| 环境/路径 | 本次可说明的能力 | 验证边界 |
|---|---|---|
| 读取 Agent Skills 格式的 agent | 可读通用入口、角色协议和用户中转步骤 | 格式可移植不等于宿主提供会话工具 |
| 当前 macOS Python 环境 | 配置隔离、状态守卫、有限返工、验收指纹、本地作业保护 | 以 VALIDATION 中实际测试为准 |
| Codex 桌面原生双聊天 | 已实测同一子会话 Luna/high → Sol/max、活动父侧双向消息、一次受控返工、独立验收和 idle 收尾 | 仅本地普通模式三轮测试；主侧主动换型、离线唤醒和 goal 未测，见 VALIDATION_E2E_20261027.md |
| Codex CLI/其他受管子代理 | 按当前宿主能力核对模型、委派许可、身份与生命周期 | 未在这些宿主做真实端到端测试 |
| WorkBuddy 5.8.3 macOS | 本地导入、原生卸载后重新导入、新聊天 Skill 调用，以及前台 Agent 同身份恢复、模型请求参数选择、同步交接、一次受控返工和 10/10 独立验收已实测 | 同名直接重复导入未覆盖；命名后台路径未通过、SendMessage 未测；实际型号 unknown、独立强度字段缺失；市场/云端未测，见 VALIDATION_WORKBUDDY_20261027.md、VALIDATION_WORKBUDDY_REIMPORT_20261028.md |
| WorkBuddy 5.9.3 macOS | 同一新MIT市场ZIP原生重装与13文件核对通过；完整前台子代理E2E通过：3次调用、2次同身份恢复、探针回忆、模型请求选择、同步交接、一次受控返工与主侧及Codex独立10→9→10，41项检查通过 | 同名直接导入仍未更新；型号只证明请求接受，实际后端unknown、无独立强度字段；SendMessage/命名后台/云端未复验，见 VALIDATION_WORKBUDDY_593_E2E_20261028.md |
| 无会话 API 或无委派权限 | 用户手动开第二聊天并中转契约和结果 | 无自动发送、守护或后台唤醒承诺 |
| Windows | 可读协议；可尝试无 POSIX 依赖的配置/消息助手 | 未测试；supervision/job_guard 不能直接作为原生 Windows 支持 |

“任意 agent”指协议可由支持文本指令/技能的 agent 使用；完整自动执行取决于实际会话与控制能力。不能把包可读取宣传成所有客户端都能自动切换模型。

2026-10-28 已填写署名并新增MIT LICENSE，新市场候选含13文件，协议正文及原11个配套运行文件与已验证r3不变。新市场包已在5.9.3原生导入、真实调用并完成上述前台E2E，取得精确绑定该ZIP的客户端white/low检测回执。5.8.3历史证据单独保留；平台解析、审核、发布及云端没有新增结论。测试准备、macOS执行器和报告问题已纠正并留存，未修改ZIP来转移验收对象。

## 旧版 luna-exec

本次保留旧入口名和既有 scripts 路径，原 v1 session、run_id、threadId、模型授权、预算、未消费指导及后台作业不迁移、不重启。旧版 references/executor.md、goal-mode.md、supervision.md、efficient-review.md 只服务已经按旧契约启动的运行。

新版通用包使用 references/executor-portable.md、protocol.md、adapters.md 和 codex.md。旧入口的 SKILL.md 对新运行导航到通用协议；继续已有旧运行时优先读取原契约及旧协议。旧角色配置 luna-worker.toml 保留给原有调用者，它不是通用版默认。

消息助手没有 session_version 时按 v1 处理，worker 模型与强度仍须非空；v2 允许单侧字段为 null 并省略对应覆盖，parent 两种格式都不传模型覆盖。v2 的非 Codex adapter 不能误用 Codex 消息 JSON。

若用户要在旧运行中换模型，先暂停受影响写入、检查活动作业和目标、记录最新授权，使用宿主真实控制恢复同一身份，再核对新轮次。既有成果按输入/依赖有效性复用。不得靠初始化新配置覆盖旧记录；升级协议或模式需要具体迁移契约，不随安装自动发生。

本次只维护技能文件和本地发布材料，不向任何已有运行发消息，也不更改应用数据库或启动实验。
