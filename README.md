# 双会话执行 / Dual Session Exec

**用强模型想，用轻模型干，省 token。**

主会话用较强的模型做规划与验收，子会话用轻量模型（例如 Luna）做执行。贵的推理只花在需要判断的地方，大量读文件、改代码、跑测试的体力活交给便宜的模型。

MIT 许可 · 1.0.0 · 免费

## 一键安装

```sh
curl -fsSL https://raw.githubusercontent.com/ChangyuZeng/dual-session-exec/main/install.sh | sh
```

默认装到 `~/.agents/skills/`，本机已有 `~/.codex/skills`、`~/.claude/skills`、`~/.workbuddy/skills` 时也会同步装上；同名旧目录会先自动备份。指定目录：

```sh
curl -fsSL https://raw.githubusercontent.com/ChangyuZeng/dual-session-exec/main/install.sh | DSE_DIR=/path/to/skills sh
```

手动安装：下载 [Release](https://github.com/ChangyuZeng/dual-session-exec/releases) 里的 zip，把 `dual-session-exec/` 目录放进 agent 的技能目录；或者直接让 agent 读取 `dual-session-exec/SKILL.md`。

**让 agent 自己装**：把这句话发给它即可。

> 运行 `curl -fsSL https://raw.githubusercontent.com/ChangyuZeng/dual-session-exec/main/install.sh | sh` 安装 dual-session-exec 技能，然后读取它的 SKILL.md。

## 职责分工

| | 主会话（强模型） | 子会话（轻量模型，如 Luna） |
|---|---|---|
| 做什么 | 规划、冻结契约、协调、难题接管、独立验收 | 按契约实现、自测、交回原始证据 |
| 不做什么 | 不亲自写大段实现 | 不改计划、不自我验收、不改主会话模型 |
| 上下文 | 只看契约、差异和证据摘要 | 承担读代码、改文件、跑命令的长上下文 |

## 为什么省 token

1. **贵模型只干少量高价值的活。** 一个任务里，真正需要强推理的是拆解计划和判断对错；大部分 token 花在读文件、写代码、看日志上。这部分交给轻量模型，按更低的单价计费。
2. **主会话上下文保持很短。** 子会话只回传「契约版本 + 差异 + 证据路径」，不把整段日志和代码塞回主会话，主会话每轮的输入 token 不会随任务越滚越大。
3. **只传差异，不重复发全文。** 同一个执行身份持续复用，后续交接只发变化部分，避免反复重建上下文。
4. **返工有上限。** 同一问题子会话最多返工一次，再失败就由主会话接管，不让轻模型在死循环里烧 token。

**预期效果**：任务越长、执行部分越重，节省越明显，因为大头 token 从强模型挪到了轻模型上。具体省多少取决于你选的两侧模型价差和任务结构，本项目不承诺固定比例；技能会如实记录两侧的配置和可得的用量，方便你自己对比。

## 快速调用

```text
使用双会话执行刚才批准的计划。主会话用当前强模型负责规划和验收，子会话用 Luna 执行和自测。
```

不确定有哪些模型可选时：

```text
使用双会话执行已批准的计划。主会话沿用当前模型；请列出可用的执行模型和强度让我选。
```

宿主不支持自动开第二个会话时，技能会生成中转消息，由你在两个聊天之间转交，不会假装已经发送。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `dual-session-exec/` | 技能本体：SKILL.md、协议、宿主适配、辅助脚本 |
| `install.sh` | 一键安装脚本 |
| `tests/` | 单元测试 |
| `tools/build_release.py` | 打包脚本 |
| `publishing/` | 市场元数据 |

## 运行要求

任何能读取 SKILL.md 的 agent 都能用。可选脚本需要 Python 3.11+；状态锁和作业守护需要 macOS 或 Linux。已在 Codex 和 WorkBuddy（macOS）上实测。

## 开发

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_release.py --out dist/build
```

## 反馈

欢迎在本仓库开 Issue。
