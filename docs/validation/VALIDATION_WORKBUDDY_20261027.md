# WorkBuddy 本地导入与前台子代理闭环通过，后台路径未通过

2026-10-28 更新：已确认直接同名导入不覆盖；经界面卸载后用原 r3 ZIP 重新导入，12 文件验证及新聊天实际 Skill 调用均通过。此前关于“重复导入未确认”的现场记录保留为历史，当前安装状态以 [替换与调用验证报告](VALIDATION_WORKBUDDY_REIMPORT_20261028.md) 为准。

2026-10-27，腾讯 WorkBuddy 5.8.3（com.tencent.workbuddy.mac）。用户要求继续并先换其他可用模型后，已将当前聊天界面从 Step-5-Preview 切为 DeepSeek-V4.1-Flash。没有修改全局模型或安全配置，没有发布；署名、许可、定价继续暂缓。

## 实测结果

| 项目 | 结果 |
|---|---|
| 通用 ZIP 本地导入、启用、技能加载 | 初次包通过；r3 直接重复导入未覆盖，后经原生卸载/重新导入通过，见 2026-10-28 报告 |
| 前台执行者恢复 | 同一 agent handle、同一原生子会话，三次 resume 的历史和身份连续性已核对 |
| 子侧模型选择 | 实现请求 DeepSeek-V4.1-Flash，返工请求 MiniMax-M3.1-Flash；调用接受参数并执行。真实后端型号 unknown |
| 两侧独立思考强度 | 当前注入工具未提供该字段，记录 unsupported，未传虚构参数 |
| 消息交接 | 前台 Agent 的请求/resume 与同步原生返回已通过；SendMessage 未测 |
| 实现与自测 | 子侧两轮均 10/10，真实 stdout/stderr/退出码保留 |
| 主侧独立验收 | 首次 10/10；主侧受控注入后 9/10，仅 unicode_casefold 失败；唯一返工后 10/10 |
| 外部测试驱动复验 | Codex 单独运行冻结验收，10/10，exit 0 |
| 收尾 | 三次前台调用均已返回；TaskOutput 无运行中后台任务，TaskList 无共享任务 |

受控缺陷由主侧明确注入，用于验证拒绝和一次返工；不能归因于执行模型自然生成错误。最终 labels.py 与注入前快照逐字节相同，冻结验收脚本 SHA 未变。该测试不构成模型质量、速度或费用对比。

## 失败与修复均保留

首轮 Step-5-Preview 尝试被客户端标记“用户已取消”，尚未创建执行者；Codex 没有点击停止，实际取消来源 unknown。换模型后，命名后台 Agent 虽返回 Spawned successfully，成员面板随后显示“已中断”，TaskOutput 查无该任务；无就绪回传，根因 unknown，后台路径未通过。

将 name@team 复合 ID 传给前台 resume 后得到不同的 agent-UUID 与新的子记录，不能据此认定原执行者身份找到。本次保留旧轮失败，在新运行中明确绑定成功前台检查得到的普通 Agent handle，再用同一 handle 验证原生会话与上下文连续性。没有把新身份伪装成旧命名成员。

前台路径还暴露：Agent 主侧工具结果只返回最后一条 final，中间的普通 assistant 消息未透出。主侧曾因缺失上下文确认而停止；独立原生记录审查发现 Read 前确有确认，且历史、handle 与原生 sessionId 一致，补充证据后继续。最初停止报告和状态已留快照。

技能的 WorkBuddy 说明已补充身份类别、前台恢复、最终回传必需信息和父轮等待要求，澄清宿主默认继承。源目录与 Codex/WorkBuddy 安装同步；五个辅助程序逻辑未改。构建器仅修正状态文字，避免将“构建不执行宿主测试”误写成全局“尚未测试”；相关 3 项构建测试通过。

## 包与证据

旧 dist/local-draft 包保留，不能作为最新修正版。r2 是此前打包快照，未单独重导入；本次 r3 含 12 个公开技能文件，再次通过原生入口上传并进入安全检测，未点击“跳过检测”。随后窗口回到空上传状态，未捕获最终扫描判定或覆盖安装确认，_user_meta 的安装时间仍为首次导入时间。因此最新重复导入不计成功。当前安装的 12 个技能文件与 r3 ZIP、源码及 Codex 安装逐字节相同，来自此前的本地同步；不能用这次比对冒充重新导入成功。已安装列表中 dual-session-exec 仍为 on。本地导入不要求市场展示署名字段；市场审核仍未执行。

- [机器可读总览](VALIDATION_WORKBUDDY_20261027.json)。
- [r3 包与界面核对](.work/workbuddy-e2e-20261027-01/evidence/r3-package-and-ui-observation.json)。
- [最新通用 ZIP](dist/workbuddy-local-test-20261027-r3/dual-session-exec-1.0.0-portable.zip)。
- [WorkBuddy 实际运行结果](.work/workbuddy-e2e-20261027-01/foreground-02/runtime-result.json)、[外部独立审计](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/driver-final-audit.json)。
- [父侧原生工具调用](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/native-parent-tool-trace.json)、[子侧原生工具调用](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/native-child-tool-trace.json)，导出排除 reasoning 与 providerData。
- [原生身份连续性证据](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/driver-identity-continuity.json)、[注入记录](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/injection-record.json)。
- [后台中断诊断](.work/workbuddy-e2e-20261027-01/evidence/worker-interruption-diagnostic.json)、[原身份误判纠正](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/correction-identity-probe.json)。
- [取消现场](.work/workbuddy-e2e-20261027-01/evidence/runtime-cancellation.json)、[缺证停止快照](.work/workbuddy-e2e-20261027-01/foreground-02/evidence/runtime-result.identity-gate-stop.snapshot.json)。

本地导入入口参考 [WorkBuddy 官方技能说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)；市场字段另见 [上架文档](https://open.workbuddy.cn/docs/skill)。本结果只覆盖当前客户端、当前前台受管代理与测试契约；后台自动通信、其他客户端版本、原生独立聊天、持久 goal 与市场审核均未通过本轮测试。真实后端型号、供应商金额与完整用量仍 unknown。
