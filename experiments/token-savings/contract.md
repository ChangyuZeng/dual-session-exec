# Contract: token-savings mini-review (contract v1)

Topic: LLM agents and tool use. Deliverable: 12 structured per-paper summaries plus one synthesis review with a comparison table.

## Fixed inputs (verified on arxiv.org/abs on 2026-10-29, latest version at that date)

Read ONLY these exact versions, e.g. `https://arxiv.org/abs/2210.03629v3` and `https://arxiv.org/pdf/2210.03629v3`.

| ID | arXiv | Version | Title |
|---|---|---|---|
| P01 | 2210.03629 | v3 | ReAct: Synergizing Reasoning and Acting in Language Models |
| P02 | 2302.04761 | v1 | Toolformer: Language Models Can Teach Themselves to Use Tools |
| P03 | 2303.11366 | v4 | Reflexion: Language Agents with Verbal Reinforcement Learning |
| P04 | 2303.17580 | v4 | HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in Hugging Face |
| P05 | 2305.15334 | v1 | Gorilla: Large Language Model Connected with Massive APIs |
| P06 | 2307.16789 | v2 | ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs |
| P07 | 2305.16291 | v2 | Voyager: An Open-Ended Embodied Agent with Large Language Models |
| P08 | 2304.03442 | v2 | Generative Agents: Interactive Simulacra of Human Behavior |
| P09 | 2308.08155 | v2 | AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation |
| P10 | 2405.15793 | v3 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering |
| P11 | 2308.03688 | v3 | AgentBench: Evaluating LLMs as Agents |
| P12 | 2307.13854 | v4 | WebArena: A Realistic Web Environment for Building Autonomous Agents |

## Arms

- **Dual (dual-session-exec):** main session plans and accepts only; sub-session reads and writes. Models in `models.md`.
- **Control:** one session with the main model does everything, same prompts and same template/checklist.

## Phases (dual arm)

1. `plan` (main): write `plan.md` in the arm output dir: reading order, what to extract, acceptance thresholds. Main must not read the papers.
2. `ready` (sub): read contract, template, checklist, plan; confirm readiness.
3. `summarize P01..P12` (sub, one paper per turn): fetch the pinned version, write `summaries/Pxx.md` from `summary-template.md`, self-check against the checklist.
4. `accept Pxx` (main, one turn per paper): judge the summary file against `acceptance-checklist.md` WITHOUT re-reading the paper; may spot-check one claim via the abstract page only. Output a JSON verdict.
5. `synthesis` (sub): write `review.md` (comparison table over all 12 + 600–1200 word synthesis).
6. `final acceptance` (main): score the whole deliverable with the checklist (0–100).

Rework budget: at most ONE rework in the entire arm (any per-paper or the synthesis). After that, failures are recorded, not reworked.

## Rules

- Write only inside this arm's output directory under `runs/<run_id>/<arm>/`.
- Never invent citations, numbers or results; mark `not stated` when the paper does not say.
- Token numbers come only from Codex session logs (`~/.codex/sessions/**/rollout-*.jsonl`, `token_count` events) via `collect_metrics.py`. Never estimated.
- Expected turns: dual ≈ 30–32 (1 plan + 1 ready + 12 summaries + 12 accepts + 1 synthesis + 1 final + ≤1 rework), control ≈ 16.
- Stop conditions: a model unavailable, auth failure, or 3 consecutive failed Codex calls → stop and record.
- Codex CLI has no cross-thread messaging tool, so the relay between the two persistent sessions is done by `orchestrate.py` (one `codex exec` session per side, continued with `codex exec resume <thread_id>`). Adapter recorded as `codex-cli-relay`.
