# WorkBuddy 5.9.3：当前MIT市场ZIP完整子代理E2E

2026-10-28，腾讯WorkBuddy 5.9.3 macOS（com.tencent.workbuddy.mac）。**当前13文件MIT免费市场ZIP的前台受管子代理闭环限定通过**：模型参数选择、同身份恢复、同步原生交接、一次受控返工和主侧独立验收均有真实证据。主侧验收10→9→10，Codex独立重放也为10→9→10；最终检查41/41。未提交审核或发布，未设置平台价格。

## 精确对象与范围

- [本次市场ZIP](dist/workbuddy-market-mit-free-20261028/dual-session-exec-1.0.0-workbuddy.zip)，SHA256 `1d0d7846525e563a6984c20b4c8acd3faccfbc90d34cf53b08b9e4c3a737f514`；包和安装目录13文件始终逐字节一致。
- 署名「双会话工坊（Dual Session Workshop）」、MIT、1.0基础版免费且无订阅均保留。此次没有修改技能正文、脚本或ZIP；包内5.8.3说明是历史实测记录，新增5.9.3结论保存在包外报告。
- 仅对隔离Python小任务normalize_labels执行技术闭环，不代表复杂项目质量、速度、节省比例、云端或任意宿主已验证。另附portable ZIP哈希不同，本轮没有原生导入该变体。
- 主会话 `<redacted-id>`；canonical run_id `<redacted-id>`，测试编号别名 `<redacted-id>`。

## 真实模型控制、身份和交接

主侧UI为DeepSeek-V4.1-Flash。子侧3次前台Agent请求依次为DeepSeek-V4.1-Flash（只读ready）、DeepSeek-V4.1-Flash（同身份实现）、MiniMax-M3.1-Flash（同身份唯一返工），max_turns分别6/12/8，run_in_background均false，未传name/team_name或扩权mode。请求全部接受并执行；真实供应商后端仍unknown，双方runtime_confirmation保持null。子侧宿主上下文中的型号声明只单独记录，不作为后端实证。

3次调用返回同一handle `<redacted-id>`，2次resume均使用它；原始子记录只有一个native sessionId `<redacted-id>`，保留3轮用户输入和原工具历史。ready用真实Python随机生成探针；后两轮提示不重复探针值、所读契约也不含探针，子侧两次从历史准确回忆。没有创建替代执行者。

交接走前台Agent请求/resume和同步工具返回。就绪、身份边界、探针、证据路径及暂停写入均在最后final中，实际父侧回执可见。该结果不算SendMessage双向通信测试。当前schema无独立effort/thinking字段，记录unsupported并省略；没有将reasoning/lite当作强度。

## 实现、自测与独立验收

冻结只读acceptance.py，SHA256 `8338c9e473f02a5984b6a297f9d3b7589ee91d86144d713a5904c5afbb23daeb`。10项行为检查覆盖list/元素类型拒绝、strip/casefold、去空去重、顺序、新对象和不改输入。子侧在task/实现labels.py和自己的测试，round1/round2自测均10/10、exit 0。

主侧亲自查看源码，并通过独立Python subprocess.run(timeout=30)运行冻结验收，真实stdout/stderr/退出码分别保存。子侧自测及其额外参考验收不替代父侧验收。

| 阶段 | 主侧实际结果 | Codex独立重放 | 文件与归因 |
|---|---|---|---|
| 子侧首次交付 | 10/10，exit 0 | 正确快照10/10 | labels.py SHA256 ecb91a2b24b63f6b201b32bb69cebbfe5f514bb68754b46a87c469ff30eaa175 |
| 父侧附加受控故障 | 9/10，exit 1；只失败unicode_casefold | 注入快照9/10，同一失败 | 追加8行；SHA256 995724fbe767240672e8acb792ec6ae40da691398f1de3e49511d9d17ae00c2c；归因parent-test-fixture |
| 同身份唯一返工后 | 10/10，exit 0 | 当前实际代码10/10 | 仅移除8行注入，逐字节回到首次正确SHA；测试和冻结验收未改 |

唯一worker_retry为issue_id=wb593:injected-unicode、request_id=retry:1。状态中只有这一次resolution_history及一次消费记录；没有改名重置额度。受控注入不是自然模型错误，也不作为模型能力或质量比较。

## 发现的问题、修复与证据保留

1. **测试准备的编号未对齐。** 预先冻结的测试编号被写入契约/session，但supervision init会另生成状态run_id。驱动独立预检发现后保留现场，主侧以状态生成ID为canonical，增加契约v2和旧编号别名；v1不改，同一子代理保留，未重init状态、未重置返工次数。这是测试记录准备问题，没有据此改技能脚本。
2. **macOS无GNU timeout。** 首次父验收包装在执行验收前就失败；原文件保存的是EXIT=127及command not found，外层shell最后返回0不能冒充验收成功。父侧保存全部失败输出，改用已有Python的subprocess.run(timeout=30)，没有安装工具或改变环境。后续三阶段均使用该执行器。
3. **报告元数据不可靠。** 手填时间出现未来值；session把上下文声明放入runtime_confirmation，与主报告的null不一致；TaskList字段被写成后台任务统计。完整原件快照后，主侧仅修报告：用原生事件时间窗口和accepted状态迁移时间、保留真实后端null、分开共享清单与本轮前台作业范围。原始worker记录/工具回执/state和代码未改；纠正期间没有唤醒子代理。
4. **驱动审计的解析假设错误。** 首次审计把失败退出码文件当成纯数字，未识别EXIT=127，导致40/41。保留该失败审计后修正解析，重新核对为41/41，原始文件和执行未变。没有通过改写原始退出码凑出通过。

## 收尾和不能扩大的结论

权威state中所有待办done、parent=accepted、worker writes_paused=true、jobs为空；3次前台调用全部返回。TaskList返回No tasks found，仅表示共享任务清单为空；本轮没有创建后台Agent、团队、goal或定时任务，没有主机全局后台普查结论，也没有唤醒已空闲子代理来确认结束。所有运行时间以原生事件为准，手填旧值已封存在快照中。

命名后台路径此前未通过，本轮没有复验；SendMessage、原生独立聊天、goal/离线唤醒、云端、Windows及其他宿主仍未验证。真实后端、供应商金额及完整token用量unknown。没有发布、提审、云端上传、全局设置或权限变更；平台解析与展示素材仍待后续授权，submission_ready保持false。

## 可复核证据

- [机器摘要](VALIDATION_WORKBUDDY_593_E2E_20261028.json)、[41项独立最终审计](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-final-audit.json)。
- [原始父工具回执](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-native-parent-tool-trace.json)、[原始子工具回执](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-native-child-tool-trace.json)，已排除reasoning、providerData及其他聊天。
- [同身份及探针核对](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-identity-continuity.json)、[原生时间线](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-native-timeline.json)。
- [Codex独立重放](.work/workbuddy-593-mit-e2e-20261028-01/evidence/driver-replay/independent-replay-result.json)、[正确快照](.work/workbuddy-593-mit-e2e-20261028-01/snapshots/round1-correct/labels.py)、[注入快照](.work/workbuddy-593-mit-e2e-20261028-01/snapshots/round2-injected/labels.py)。
- [原生父会话最终结果](.work/workbuddy-593-mit-e2e-20261028-01/runtime-result.json)、[权威状态](.work/workbuddy-593-mit-e2e-20261028-01/state.json)、[配置身份](.work/workbuddy-593-mit-e2e-20261028-01/session.json)。
- [编号对齐](.work/workbuddy-593-mit-e2e-20261028-01/evidence/parent/run-id-alignment.json)、[报告纠正](.work/workbuddy-593-mit-e2e-20261028-01/evidence/parent/report-metadata-correction.json)、[纠正前快照](.work/workbuddy-593-mit-e2e-20261028-01/snapshots/pre-report-metadata-correction)。

所有私有运行、原始记录与备份均留在.work，未装入13文件ZIP。5.8.3历史闭环与此前5.9.3安装调用记录保持不动，本报告追加当前同一市场包的新证据。
