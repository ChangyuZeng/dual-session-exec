#!/usr/bin/env python3
"""Read token usage from Codex session logs. Usage: collect_metrics.py RUN_DIR  -> appends rows to metrics.csv"""
import json, sys, glob, os, pathlib, csv
HERE = pathlib.Path(__file__).resolve().parent; run = pathlib.Path(sys.argv[1]).resolve()
REQ = {"main": ("gpt-6.1-sol","max"), "single": ("gpt-6.1-sol","max"), "sub": ("gpt-6.1-terra","medium")}
rows = []
for arm in ("dual","control"):
    sp = run/arm/"orchestrator-state.json"
    if not sp.exists(): continue
    st = json.load(open(sp))
    for side, sid in st["sessions"].items():
        f = glob.glob(os.path.expanduser(f"~/.codex/sessions/**/rollout-*{sid}.jsonl"), recursive=True)[0]
        tot, models, efforts, turns = {}, set(), set(), 0
        for line in open(f):
            e = json.loads(line); p = e.get("payload", {})
            if e.get("type") == "turn_context":
                turns += 1; models.add(p.get("model")); efforts.add(str(p.get("effort") or p.get("reasoning_effort")))
            if p.get("type") == "token_count" and p.get("info"): tot = p["info"]["total_token_usage"]
        secs = sum(t["secs"] for t in st["turns"] if t["side"] == side)
        score = (st.get("final") or {}).get("final_score", "") if side in ("main","single") else ""
        rows.append([run.name, arm, side, sid, *REQ[side], "|".join(map(str,models)), "|".join(efforts),
            tot.get("input_tokens"), tot.get("cached_input_tokens"), tot.get("output_tokens"), tot.get("reasoning_output_tokens"),
            tot.get("total_tokens"), turns, round(secs,1), st.get("rework_used",0), score])
with open(HERE/"metrics.csv","a",newline="") as fh: csv.writer(fh).writerows(rows)
for r in rows: print(r)
