# Models (exact Codex ids, from ~/.codex/magpie-desktop-models.json via config.toml model_catalog_json; codex-cli 0.164.0)

| Role | Model id | Reasoning effort | Why |
|---|---|---|---|
| Dual main | `gpt-6.1-sol` | `max` | "GPT-6.1 SO" = GPT-6.1-Sol; `max` is the named maximum level requested (catalog also lists `ultra` above it). |
| Dual sub | `gpt-6.1-terra` | `medium` | No model named "6.1 Taro" exists in the catalog; `gpt-6.1-terra` (display "GPT-6.1 Terra") is the closest match and assumed to be the intended one. Fallback would be `gpt-6-luna` (no 6.1 Luna exists). |
| Control | `gpt-6.1-sol` | `max` | Same as dual main. |

Requested config is recorded here; the actually-used model/effort per turn is read from `turn_context` in each session log and written to `metrics.csv` (column `observed_model`).
