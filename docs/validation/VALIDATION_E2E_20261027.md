# 当前 Codex 真实端到端测试：通过

2026-10-27，普通模式；唯一测试聊天「双会话技能端到端测试｜配置、交接与返工」，threadId：<redacted-id>。

| 检查 | 实际结果 |
|---|---|
| 主会话配置 | gpt-6.1-sol / xhigh，始终保留 |
| 子会话准备、首轮实现 | gpt-6-luna / high，真实 turn_context 核对 |
| 同一子会话返工 | gpt-6-sol / max；旧确认失效，新轮次重新观察 |
| 消息 | 主→子 start:1、retry:1；子→主 delivery:1、delivery:2，均有工具回执和实际处理证据 |
| 自测与独立验收 | 子侧两次各 7 项通过；主侧首次 10/10，注入后 9/10 拒绝，返工后 10/10 通过 |
| 返工 | 同一 issue 一次 worker_retry，消费一次；恢复文件与首轮正确快照一致 |
| 收尾 | 子会话 idle，写入暂停，jobs=[]；全部待办 done，父侧 accepted，监督 closed，期限已清空 |
| 封存 | 独立验收回执 check：reusable=true、changed=[] |

缺陷是契约事先声明、由父侧在隔离测试模块中注入的，用于测试真实拒绝和返工，不是执行模型自然出错，也不衡量模型质量。

真实测试发现并修正了三处协议说明：状态更新 JSON 必须直接放根层字段（首次错误包装被接口拒绝，原始失败保留）；recovery 只接受四个真实字段；Codex 运行配置与消息接收要按真实元数据格式取证，不能只查 user 角色或复制请求值。修正已同步源目录和安装目录，相关 JSON 示例实际验证通过。辅助脚本逻辑未改动。

完整证据在 [.work/e2e-codex-20261027-01/](.work/e2e-codex-20261027-01/)：

- [契约](.work/e2e-codex-20261027-01/contract.md)、[主会话独立验收报告](.work/e2e-codex-20261027-01/acceptance-report.md)。
- [模型与消息检查](.work/e2e-codex-20261027-01/evidence/final-checks.json)、[实际接收回调](.work/e2e-codex-20261027-01/evidence/parent-received-messages-callbacks.json)。
- [最终状态](.work/e2e-codex-20261027-01/accepted-state.json)、[监督退出检查](.work/e2e-codex-20261027-01/supervision-final-check.json)、[封存回执](.work/e2e-codex-20261027-01/item-accepted-v1.json)。
- [机器可读总览](VALIDATION_E2E_20261027.json)。原始命令、自测、拒绝、状态更新失败、消息参数及发送回执均单独保留。

子会话客户端累计计数：input_tokens=1,526,584（cached_input_tokens=1,359,232），output_tokens=16,869，total_tokens=1,543,453；它包括多个工具续轮的重复上下文，是客户端统计，不是计费金额。主侧没有在测试起点冻结累计用量基线，因此本轮精确增量为 unknown；提供商金额 unknown。未据此声明节省 token、费用、耗时或质量优势。

本次只验证当前 Codex 活动主会话、原生独立子会话、普通模式和上述三轮流程。主会话通过 UI 主动更换型号、离线唤醒、goal 模式、重复投递注入、其他 agent 及 WorkBuddy 尚未测试。没有发布、上传或归档聊天。旧 dist/local-draft/ 是初次打包快照，不含本次协议修正；当前使用源目录或已安装技能，正式分发前再构建新包。
