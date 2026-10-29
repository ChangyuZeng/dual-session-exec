#!/usr/bin/env python3
"""Relay driver for the token-savings experiment. Usage: orchestrate.py dual|control RUN_DIR"""
import json, subprocess, sys, time, re, pathlib
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
SKILL = REPO / "dual-session-exec"
MAIN = ("gpt-6.1-sol", "max"); SUB = ("gpt-6.1-terra", "medium")
PAPERS = [l.split("\t") for l in (HERE/"papers.tsv").read_text().splitlines()[1:]]
arm, run = sys.argv[1], pathlib.Path(sys.argv[2]).resolve()
out = run/arm; (out/"summaries").mkdir(parents=True, exist_ok=True); (out/"turns").mkdir(exist_ok=True)
state = {"arm": arm, "sessions": {}, "turns": [], "rework_used": 0, "verdicts": {}, "started": time.time()}
def save(): (out/"orchestrator-state.json").write_text(json.dumps(state, indent=1, ensure_ascii=False))
def log(msg): print(time.strftime("%H:%M:%S"), msg, flush=True)
def codex(side, model, prompt):
    n = len(state["turns"]) + 1; tag = f"{n:02d}-{side}"
    last = out/"turns"/f"{tag}.last.txt"
    base = ["-m", model[0], "-c", f'model_reasoning_effort="{model[1]}"', "-c", 'approval_policy="never"',
            "-c", 'sandbox_mode="workspace-write"', "-c", "sandbox_workspace_write.network_access=true",
            "--skip-git-repo-check", "--json", "-o", str(last)]
    sid = state["sessions"].get(side)
    cmd = (["codex", "exec", "resume"] + base + [sid, "-"]) if sid else (["codex", "exec"] + base + ["-C", str(REPO), "-"])
    for attempt in range(3):
        t0 = time.time()
        p = subprocess.run(cmd, input=prompt, text=True, capture_output=True)
        (out/"turns"/f"{tag}.jsonl").write_text(p.stdout); (out/"turns"/f"{tag}.stderr").write_text(p.stderr)
        if not sid:
            m = re.search(r'"thread_id"\s*:\s*"([^"]+)"', p.stdout)
            if m: sid = state["sessions"][side] = m.group(1)
        if p.returncode == 0: break
        log(f"{tag} failed rc={p.returncode} attempt {attempt+1}")
    else:
        state["stopped"] = f"{tag}: 3 consecutive failures"; save(); sys.exit(2)
    state["turns"].append({"tag": tag, "side": side, "secs": round(time.time()-t0, 1)}); save()
    log(f"{tag} done ({state['turns'][-1]['secs']}s) session={sid}")
    return last.read_text() if last.exists() else ""
def verdict(txt):
    m = re.findall(r'\{[^{}]*"(?:paper|final_score)"[^{}]*(?:\{[^{}]*\}[^{}]*)?\}', txt, re.S)
    try: return json.loads(m[-1])
    except Exception: return {"raw": txt[-500:]}
CTX = f"""Experiment files: contract {HERE}/contract.md, template {HERE}/summary-template.md, checklist {HERE}/acceptance-checklist.md.
Arm output dir (the ONLY place you may write): {out}"""
if arm == "dual":
    ROLE_M = f"You are the MAIN session of a dual-session-exec run (skill: {SKILL}/SKILL.md). You plan and accept only; you never read the papers or write summaries.\n{CTX}"
    codex("main", MAIN, ROLE_M + f"\nPhase plan: read the contract, template and checklist, then write {out}/plan.md (reading guidance per paper, extraction priorities, acceptance thresholds). Reply with a one-paragraph plan summary.")
    codex("sub", SUB, f"You are the SUB (executor) session of a dual-session-exec run. Executor entry: {SKILL}/references/executor-portable.md.\n{CTX}\nPhase ready: read the contract, template, checklist and {out}/plan.md. Do not summarize yet. Reply READY plus any question.")
    for pid, ax, v, title in PAPERS:
        f = out/"summaries"/f"{pid}.md"
        codex("sub", SUB, f"Start item summarize-{pid}: fetch https://arxiv.org/pdf/{ax}{v} (fallback https://arxiv.org/abs/{ax}{v}), read it, write {f} following the template, self-check against the checklist. Reply 'delivered {pid}' plus self-score.")
        r = codex("main", MAIN, f"Accept item {pid} ({ax}{v}). Read {f} only (you may open https://arxiv.org/abs/{ax}{v} to spot-check one claim). Grade with the per-paper checklist. Reply with exactly one verdict JSON line.")
        vd = verdict(r); state["verdicts"][pid] = vd; save()
        if vd.get("pass") is False and state["rework_used"] == 0:
            state["rework_used"] = 1
            codex("sub", SUB, f"Rework (the only one allowed in this run) for {pid}. Issues: {json.dumps(vd.get('issues'))}. Fix {f}. Reply 'delivered {pid} rework'.")
            state["verdicts"][pid+"-rework"] = verdict(codex("main", MAIN, f"Re-accept {pid} after rework. Reply with one verdict JSON line.")); save()
    codex("sub", SUB, f"Phase synthesis: using only {out}/summaries/*.md, write {out}/review.md with a comparison table over P01-P12 and a 600-1200 word synthesis as the checklist requires. Reply 'delivered review'.")
    r = codex("main", MAIN, f"Final acceptance: read {out}/review.md and all summaries; score with the final checklist (F1 uses your per-paper verdicts: {json.dumps(state['verdicts'])}). Reply with one final JSON line.")
    state["final"] = verdict(r)
    if state["final"].get("accepted") is False and state["rework_used"] == 0:
        state["rework_used"] = 1
        codex("sub", SUB, f"Rework (only one allowed) of review.md. Main's verdict: {json.dumps(state['final'])}. Fix it.")
        state["final"] = verdict(codex("main", MAIN, "Re-score the reworked review.md. Reply with one final JSON line."))
else:
    ROLE = f"You are a single-session agent doing the whole task alone (plan, read, summarize, self-accept).\n{CTX}"
    codex("single", MAIN, ROLE + f"\nPhase plan: write {out}/plan.md. Reply with a short summary.")
    for pid, ax, v, title in PAPERS:
        f = out/"summaries"/f"{pid}.md"
        codex("single", MAIN, f"Summarize {pid}: fetch https://arxiv.org/pdf/{ax}{v} (fallback abs page), write {f} following the template, then grade it with the per-paper checklist. Reply with one verdict JSON line.")
    codex("single", MAIN, f"Phase synthesis: write {out}/review.md (comparison table + 600-1200 word synthesis) from your summaries. Reply 'delivered review'.")
    state["final"] = verdict(codex("single", MAIN, "Final acceptance: score review.md and summaries with the final checklist. Reply with one final JSON line."))
state["finished"] = time.time(); save(); log("ARM COMPLETE")
