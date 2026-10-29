# 商品页草案

2026-10-28 市场候选材料。署名、MIT许可及1.0免费/无订阅方案已由用户确认，记录见 CONFIRMATIONS_ZH.md；本页没有提交或发布。双语短简介与三个调用案例见 MARKET_METADATA.json（源文件 marketplace.json）。

## 中文

**名称：双会话执行 · 模型自由分工**

作者：双会话工坊（Dual Session Workshop）。许可：MIT。1.0基础版免费，不做订阅；平台免费设置尚未操作。

在宿主支持时，为主会话和执行会话分别选择模型与思考强度，把批准计划变成可复查的执行、自测和独立验收。适合已有明确计划，需要让另一个会话完成实现、同时保留主会话判断的人。

你提供批准计划、输入位置、允许修改的范围、验收标准、预算与停止条件；技能组织契约、阶段待办、差异交接、有限返工和最终验收报告。主会话可以保留当前配置，执行会话可以选择另一组宿主支持的配置。未指定的字段沿用各自宿主默认，不会把执行侧模型覆盖到主会话。

可用于代码修复、批量文档处理、数据检查，以及已有授权和明确预算的实验执行。结果保留完成与未完成项、原始证据、模型请求与确认状态；失败或负结果如实交付。

自动协作需要客户端支持会话创建、通信和恢复；不具备时提供用户中转步骤。当前Codex原生双会话及WorkBuddy 5.8.3/5.9.3 macOS前台子代理已完成限定实测；5.9.3使用当前13文件MIT市场包，同身份恢复、同步交接、一次受控返工及独立10→9→10通过。WorkBuddy 模型请求参数可选择，真实后端型号仍 unknown，独立思考强度字段缺失；命名后台路径未通过，SendMessage、市场和云端未测。其他客户端不能据此视为支持。完整范围见本地使用指南与验证报告，当前暂不发布。

交付内容：技能协议、角色入口、宿主适配说明、本地状态/配置/验收/作业辅助脚本及MIT许可文件。模型账号、客户端订阅及额外定制服务不包含在技能内。维护采用问题收集和尽力修复，不承诺固定响应时限或终身更新。

## English

**Dual Session Exec**

Author: 双会话工坊（Dual Session Workshop）. License: MIT. The 1.0 base edition is free with no subscription; no platform pricing setting has been applied yet.

Choose each role's model and reasoning setting where the host supports those controls. One session implements and self-tests an approved plan; the main session coordinates, handles difficult issues, and reviews the result independently.

Provide the approved plan, inputs, permitted changes, acceptance criteria, budget, and stop conditions. Receive a scoped contract, persistent checkpoints, concise handoffs, bounded rework, and an evidence-based review. Unknown runtime settings and usage remain unknown.

Automation requires host support for creating, messaging, and resuming sessions. Where those capabilities are unavailable, use a user-operated relay. Scoped tests passed for Codex native chats and WorkBuddy 5.8.3/5.9.3 macOS foreground agents. The current 13-file MIT market archive passed a 5.9.3 foreground run with identity continuity, native result handoff, one controlled retry, and independent 10/9/10 acceptance. WorkBuddy accepted the requested model parameters, but actual backend models remain unknown and independent reasoning control is unavailable in the tested tools. Its named background path did not pass; SendMessage, cloud execution, marketplace review, and other clients remain unverified. This is an unpublished local draft.

The package includes instructions, role references, adaptation guidance, local helpers, and the MIT license. It does not include model accounts, client subscriptions, or custom services. Maintenance is best effort with no fixed response deadline or promise of lifetime updates. Nothing has been submitted for review or published.

## FAQ

**能在任意 agent 上用吗？** 能读取文本协议的 agent 可按协议操作；会话工具与模型控制须另行核对。没有自动化能力时需要两个真实聊天和用户中转，单会话角色扮演不算独立验收。

**能直接把当前主会话切到指定模型吗？** 只有宿主有真实控制时才能自动完成；否则会给出用户操作要求。更改技能文本不等于切换当前模型。

**WorkBuddy 能分别设置两侧的 high/max 吗？** 当前实测工具没有独立思考强度字段，记录 unsupported 并省略参数。模型路由 reasoning/lite 不等于思考强度；真实后端型号也不能仅凭请求或 UI 标签确认。

**如何更新本地安装？** WorkBuddy 5.8.3与5.9.3 macOS同名重复导入均未覆盖。已验证的方法是完整备份该技能，使用界面卸载后重新导入，再在新聊天核对加载和版本。新MIT市场包已在5.9.3完成13文件、署名、许可及真实调用检查；同一ZIP随后在5.9.3也通过完整前台子代理E2E，真实后端、SendMessage与云端等限制保留。

**付费云端版本也验证了吗？** 没有。当前闭环和重装记录仅覆盖本地客户端。若选择付费云端交付，需另核对代理工具、运行时、目录与模型控制；不把本地成功写成云端可用。

**能保证降低成本或更快完成吗？** 没有通用保证。差异交接和验收复用减少重复上下文，实际成本、延迟和质量要用相同任务及真实用量评估。

**子会话失败后会一直重试吗？** 不会。同一问题仅一次获准返工；再次失败或诊断复杂时交回主会话。预算与停止条件一直有效。

**能接着旧 Luna 运行继续吗？** 保留原身份、契约和作业；安装不自动迁移旧运行。配置变更按兼容说明核查后再生效。
