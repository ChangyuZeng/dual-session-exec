# Token-savings experiment

Files: `contract.md`, `papers.tsv`, `summary-template.md`, `acceptance-checklist.md`, `models.md`, `metrics.csv`.

```sh
RUN=runs/$(date +%Y%m%d-%H%M%S); mkdir -p $RUN
nohup python3 orchestrate.py dual $RUN > $RUN/dual.log 2>&1 &
nohup python3 orchestrate.py control $RUN > $RUN/control.log 2>&1 &
# after both finish:
python3 collect_metrics.py $RUN
```
Tokens are read from `~/.codex/sessions` `token_count` events, never estimated. Cost = tokens × each model's price (fill prices when known).
