# 双会话执行 / Dual Session Exec

把已批准的计划交给一个执行会话实现和自测，由原主会话协调、接管困难问题并独立验收。两侧的模型与思考强度可以分别选择，不绑定特定厂商或模型。

作者：[双会话工坊（Dual Session Workshop）](https://github.com/ChangyuZeng) · 许可：[MIT](LICENSE) · 版本：1.0.0（免费，无订阅）

## 它解决什么

复杂任务里，同一个会话既要写实现，又要保留判断和验收，很容易糊在一起。这个 skill 把职责拆开：

- **主会话**：规划、协调、接管、独立验收
- **执行会话**：实现、自测、交回原始证据

按宿主实际能力，自动走原生双会话、受管子代理，或生成用户中转消息。缺少工具时不会假装已经创建、发送或恢复。

## 安装

把整个 `dual-session-exec/` 目录放到目标 agent 的技能搜索目录，或让 agent 直接读取其中的 `SKILL.md`。保留 `references/` 与 `scripts/` 的相对位置。

Codex 用户级示例：

```sh
cp -R dual-session-exec ~/.agents/skills/dual-session-exec
```

也可使用项目级目录 `.agents/skills/dual-session-exec/`。位置依据 [Codex 技能说明](https://learn.chatgpt.com/docs/build-skills)。WorkBuddy 等其他宿主按其导入界面操作。

可选脚本需要 Python 3.11+；状态锁和本地作业守护需要 macOS/Linux 等 POSIX 环境。无脚本环境仍可用用户中转协议。

## 快速调用

```text
使用双会话执行已批准的修复计划。主会话沿用当前模型和思考强度；请列出当前可用的执行模型与强度让我选择。使用普通模式，保留原预算、停止条件和独立验收。
```

已决定型号时：

```text
主会话使用我指定的模型和强度，子会话使用我指定的另一组配置，执行刚才批准的计划。先核对宿主支持情况；不能切换时说明具体操作，不自动替换。
```

## 仓库结构

| 路径 | 内容 |
|---|---|
| `dual-session-exec/` | 技能正文、宿主适配、协议与辅助脚本 |
| `compat/luna-exec/` | 旧版 `luna-exec` 兼容入口 |
| `tests/` | 单元测试 |
| `tools/build_release.py` | 本地打包脚本 |
| `docs/` | 商品说明与验证摘要 |
| `publishing/` | 市场元数据与发行决定 |

## 构建与测试

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_release.py --out dist/new-local-build
```

## 实测范围

当前有限定实测：

- Codex 原生双会话端到端
- WorkBuddy 5.8.3 / 5.9.3 macOS 前台子代理闭环

未声称覆盖：独立思考强度字段、命名后台路径、真实后端型号确认、云端与其他宿主。细节见 [COMPATIBILITY.md](COMPATIBILITY.md) 与 `docs/validation/`。

## 不做什么

- 不提供模型账号、充值、API 代理
- 不自动更换当前轮次模型
- 不代用户点击发布或提交审核
- 不承诺固定节省比例或终身更新

## 反馈

Issue 与讨论欢迎直接开在本仓库。WorkBuddy 市场反馈入口以上线后的平台为准。
