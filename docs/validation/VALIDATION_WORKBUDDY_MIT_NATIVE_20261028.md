# 新MIT市场包的WorkBuddy原生导入与调用验收

2026-10-28，腾讯WorkBuddy **5.9.3 macOS**（com.tencent.workbuddy.mac）。本次新13文件市场ZIP的原生安装与维护分支真实调用验收通过，独立检查23/23。署名为「双会话工坊（Dual Session Workshop）」，完整MIT许可正确；1.0基础版免费、无订阅的发行决定保持不变。未提交开放平台解析、审核或发布，也未设置市场价格。

## 精确验收对象

- [市场ZIP](dist/workbuddy-market-mit-free-20261028/dual-session-exec-1.0.0-workbuddy.zip)，41,798字节，13个分发文件。
- SHA256：`1d0d7846525e563a6984c20b4c8acd3faccfbc90d34cf53b08b9e4c3a737f514`。
- 安装目录：`~/.workbuddy/skills/dual-session-exec`。
- 包与安装文件未作手工同步；ZIP全程未改。另附的13文件portable变体没有在本轮原生导入，不能把此验收自动转给其他哈希的包。

## 发现的问题与处理

**同名直接导入仍未更新旧文件。** 已先完整备份旧12文件安装。5.9.3原生上传新ZIP后，日志虽有import/install OK，安装时间未变，仅11/13匹配，LICENSE仍缺失、SKILL.md仍旧。失败清单和界面记录已保留，不能称为直接覆盖成功。

随后在技能详情「更多操作 → 卸载」并确认，界面显示“dual-session-exec 已卸载”，独立检查安装目录确实消失。再次从「添加技能 → 上传技能」选择同一个市场ZIP，界面显示“技能导入成功”。新安装时间更新，13个分发文件全部与ZIP逐字节一致，宿主仅另加_user_meta.json，技能保持启用。旧安装备份留存，卸载后没有靠手工复制凑出安装结果。

**首份调用报告有三处记录错误，已在同一测试聊天修正。** 安装原件和文件哈希始终正确；错误是description_zh复制了description、MIT版权行号写成2而实际为3，以及正文字符数自述3294与原生回执独立计数2835不符。先封存原报告，再要求程序化读取8项元数据和许可行号，删除无法复核的字符数估算。纠正后的报告再次独立核对通过。此为报告纠正，不计作新的技能代码缺陷，也不替代历史工作流的一次返工测试。

## 实际原生调用与独立核对

从新版技能详情「去试试」发起隔离工作区的新聊天，实际技能标签为「双会话执行 · 模型自由分工」，界面模型为DeepSeek-V4.1-Flash。原生记录证明真正执行了Skill({"skill":"dual-session-exec"})，返回安装目录及正文；随后4次Read读取了该目录的SKILL.md、LICENSE、adapters.md、workbuddy.md。

WorkBuddy用真实工具计算13文件清单，用宿主Python 3.13.12实际运行安装目录下的scripts/session_config.py --help，捕获stdout 370字节、stderr为空、退出码0。Codex独立逐项比对ZIP、当前安装、WorkBuddy清单、8项元数据及MIT全文；另用同一Python解释器重跑帮助命令，输出一致。23项独立检查全部通过。原生界面首轮显示“已完成1m56s”，同一聊天报告纠正显示“已完成1m20s”。

维护分支没有创建Agent、团队、goal或定时任务，没有外部IM、全局配置或权限修改。它核验安装与调用，没有重跑完整实现、同身份子代理恢复或受控故障闭环。

## 新包的客户端安全检测

本次扫描精确绑定新市场ZIP的MD5 `88a7cf83318ea7ee3e5cc72c5bb2f74c`。2026-10-28T03:33:06.113Z回执为verdict=white、riskLevel=low、threatLevel=2。扫描发生在首次导入尝试，随后重装使用同一不可变ZIP；不声称重装又完成了一次新扫描。全程未点击“跳过检测，直接安装”。客户端检测不等于独立安全审计或市场审核；日志里的扫描状态store-publish不是市场发布。

## 能力边界与后续状态

5.8.3完整前台工作流的同身份恢复、模型请求参数、原生同步交接、受控10→9→10与独立10/10证据继续保留在[历史闭环报告](VALIDATION_WORKBUDDY_20261027.md)。此次5.9.3结果仅覆盖新市场包原生安装与维护调用，不能扩大为该版本全部工作流已验证。

真实后端型号仍unknown；独立思考强度字段在历史测试工具中不可用，本轮没有新增控制能力证明。命名后台路径此前未通过、SendMessage未测；云端、Windows、离线常驻、其他宿主和速度/费用收益均未由本轮验证。本地导入不会落实市场免费价格设置。submission_ready保持false，平台解析、展示素材和将来实际发布表单仍需后续处理；本轮没有提交审核或发布。

## 证据

- [机器可读摘要](VALIDATION_WORKBUDDY_MIT_NATIVE_20261028.json)、[独立最终审计](.work/workbuddy-market-mit-free-native-20261028-01/driver-final-audit.json)。
- [精确ZIP与旧安装快照](.work/workbuddy-market-mit-free-native-20261028-01/preflight.json)、[直接导入未更新](.work/workbuddy-market-mit-free-native-20261028-01/direct-native-import-files.json)。
- [原生卸载目录消失](.work/workbuddy-market-mit-free-native-20261028-01/native-uninstall-confirmed.json)、[重装后13文件比对](.work/workbuddy-market-mit-free-native-20261028-01/native-reinstall-verified.json)、[精确绑定新ZIP的检测/导入日志](.work/workbuddy-market-mit-free-native-20261028-01/native-import-log-extract.json)。
- [原生调用请求](.work/workbuddy-market-mit-free-native-20261028-01/native-invocation-request.txt)、[原始工具回执](.work/workbuddy-market-mit-free-native-20261028-01/native-invocation-tool-trace.json)，已排除reasoning、providerData及其他聊天内容。
- [纠正前报告](.work/workbuddy-market-mit-free-native-20261028-01/invocation-result.before-correction.json)、[独立审查问题](.work/workbuddy-market-mit-free-native-20261028-01/independent-review-findings.json)、[最终调用报告](.work/workbuddy-market-mit-free-native-20261028-01/invocation-result.json)。

旧安装与更新前材料完整保存在本次.work证据目录内，不进入13文件分发ZIP。历史r3、local-ready与旧市场草案保持原样。
