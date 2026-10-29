# WorkBuddy 新版替换与导入后调用验证通过

2026-10-28，腾讯 WorkBuddy 5.8.3（com.tencent.workbuddy.mac）。当前已安装原 r3 ZIP 的全部 12 个技能文件，导入后的真实 Skill 调用正常。没有发布、提交市场审核或修改全局配置；ZIP 与技能源码未改。

## 结论与实际更新方法

**当前客户端的同名直接重复导入没有覆盖旧文件；通过“备份 → 界面卸载 → 原生 ZIP 重新导入”完成了新版替换。** 不能把这次结果写成“直接覆盖安装成功”。

为了排除此前手工同步导致文件本来就相同的干扰，先完整备份安装目录，再只把安装目录中的 references/workbuddy.md 临时恢复为真实 r2 版本，作为可恢复的旧版探针。直接上传原 r3 ZIP 后，客户端日志虽显示 import/install OK，旧文件哈希仍未变化。该次失败和文件监测记录保留。

随后通过该测试技能的“更多操作 → 卸载 → 卸载确认”，界面明确显示 dual-session-exec 已卸载，安装目录独立核对为不存在。再次从原生入口选择同一 r3 ZIP 后，界面显示“技能导入成功”，新安装时间已更新，12 个文件全部与 ZIP 逐字节一致，旧版探针已由导入器恢复为 r3。卸载后没有通过手工复制或回滚凑出最终安装；完整旧安装备份仍保留。

- ZIP：dist/workbuddy-local-test-20261027-r3/dual-session-exec-1.0.0-portable.zip。
- SHA256：`6e8008e9ac9ed21a1e98da04d10fbe7a5f6178f71177d9361a18ac52872a0a7f`。
- 新版 WorkBuddy 参考文件 SHA256：`32f4727698c1f32a78080c54a28114838742669fc391faae3548f6008c4e5862`。
- 重新安装后保持启用；实际源目录为 `~/.workbuddy/skills/dual-session-exec`。

## 导入后的新聊天调用

从已安装技能详情点击“去试试”，使用独立测试工作区和实际 skill chip。原生记录显示真实调用 `Skill({"skill":"dual-session-exec"})` 完成，返回重新安装目录及技能正文；随后实际 Read 了 adapters.md、workbuddy.md，内容包含最新版前台身份恢复、最终回传规则。

WorkBuddy 实际核对 cwd、计算 12 个公开文件 SHA256，并用宿主 Python 3.13.12 运行导入目录下 `scripts/session_config.py --help`，stdout 为正常帮助信息、stderr 为空、真实退出码 0。Codex 独立比对其产出的 12 文件清单、实际安装文件与原 ZIP，全部一致。客户端最终显示“已完成 1m35s”。

此次调用是维护/检查分支，没有 Agent、TeamCreate、SendMessage 或任务启动调用；没有创建执行者、goal、定时任务、外部 IM 或发布。没有重复消耗前一轮的完整实现/返工测试。前台工作流的 10→9→10 验收证据仍见 [先前端到端报告](VALIDATION_WORKBUDDY_20261027.md)。

## 安全检测回执与边界

本次从客户端日志补齐了同一不可变 r3 ZIP 的扫描结果：MD5 `dfa22bb05868b2a624fee579918abb27`，2026-10-27T14:05:03.172Z 的 scan-completed 为 verdict=white、riskLevel=low、threatLevel=2。它是同一包先前扫描的真实回执，不能描述成重装时又重新跑了一次扫描，也不替代独立安全审计。全程没有点击“跳过检测，直接安装”。

“直接重复导入不覆盖”只是在当前客户端、当前本地入口下的实际观察。模型界面为 DeepSeek-V4.1-Flash，真实后端仍 unknown；当前工具无独立强度字段。命名后台执行者路径与市场审核仍未通过本轮验证，没有扩大前一轮兼容性结论。

## 可核对证据

- [机器可读结果](VALIDATION_WORKBUDDY_REIMPORT_20261028.json)、[独立最终审计](.work/workbuddy-reimport-20261028-01/evidence/driver-final-audit.json)。
- [原生重装与 12 文件比对](.work/workbuddy-reimport-20261028-01/evidence/native-reinstall-verified.json)。
- [导入后的实际调用结果](.work/workbuddy-reimport-20261028-01/invocation-result.json)、[原生工具调用回执](.work/workbuddy-reimport-20261028-01/evidence/native-invocation-tool-trace.json)，已排除 reasoning、providerData 与其他聊天内容。
- [旧版探针与完整备份说明](.work/workbuddy-reimport-20261028-01/evidence/controlled-preimage.json)、[直接重复导入未覆盖](.work/workbuddy-reimport-20261028-01/evidence/direct-reimport-result.json)、[文件变化监测](.work/workbuddy-reimport-20261028-01/evidence/native-overwrite-watch.jsonl)。
- [界面卸载与目录消失证据](.work/workbuddy-reimport-20261028-01/evidence/native-uninstall-confirmed.json)、[精确绑定 ZIP 的客户端扫描/导入日志](.work/workbuddy-reimport-20261028-01/evidence/native-import-log-extract.json)。
