# Acceptance checklist (score 0–100)

## Per-paper summary (each 0–10, pass ≥ 7)

| # | Criterion | Points |
|---|---|---|
| A1 | All template fields present and non-empty (or explicit `not stated`) | 2 |
| A2 | Correct paper and version in header | 1 |
| A3 | Core method accurately and specifically described | 2 |
| A4 | Evaluation has concrete benchmarks + at least one reported number with location | 2 |
| A5 | Limitations: author-stated and reviewer view distinguished | 1 |
| A6 | Cross-links to ≥1 other P-ID that make sense | 1 |
| A7 | No hallucination red flags (spot-check one claim against abstract) | 1 |

Verdict JSON: `{"paper":"Pxx","score":0-10,"pass":true|false,"issues":["..."]}`

## Final deliverable (0–100)

| # | Criterion | Points |
|---|---|---|
| F1 | Mean per-paper score × 4 (max 40) | 40 |
| F2 | Comparison table covers all 12 with consistent columns (method type, tools/env, eval, key number) | 20 |
| F3 | Synthesis identifies ≥3 cross-cutting themes with P-ID evidence | 20 |
| F4 | Open problems / gaps grounded in the papers | 10 |
| F5 | Length 600–1200 words, no invented facts | 10 |

Final JSON: `{"final_score":0-100,"breakdown":{"F1":..,"F2":..,"F3":..,"F4":..,"F5":..},"accepted":true|false}` (accepted if ≥ 70).
