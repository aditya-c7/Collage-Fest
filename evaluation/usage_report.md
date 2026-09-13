# Token Usage and Cost Analysis

Final full-dataset run that produced `output.csv` (250 requests).

## Architecture summary

- Deterministic Decimal cash-flow engine (pure Python): no model calls at
  decision time. All financial math — 90-day forecasts, safe-amount solvers,
  plan ranking, validation gates — is deterministic and replayable offline.
- Model usage is confined to unstructured-input extraction, and every response
  is cached on disk (`code/extraction_cache/`). The final run replays the cache;
  no tokens are consumed while producing `output.csv`.

## Model calls

| Provider | Model | Calls | Input tokens | Output tokens |
|---|---|---|---|---|
| Google Gemini (vision) | gemini-2.5-flash | 16 | 7696 | 586 |
| **Total** | — | **16** | **7696** | **586** |

- Total tokens (input + output): 8282
- Average tokens per request (250 requests): 33.1
- Average model calls per request: 0.064

## Cost

- All model calls ran on the Google AI Studio **free tier** (gemini-2.5-flash).
- Estimated total cost: **$0.00**; estimated per-request cost: **$0.0000**.
- For reference, at public list pricing this extraction volume would cost
  well under $0.05; the deterministic engine itself consumes no tokens.

## Replay / determinism

- `output.csv` is produced by `python code/main.py`, which reads the cached
  extractions and runs the deterministic engine. Two consecutive runs produce
  byte-identical output (verified).
- Re-running the full pipeline without an API key reproduces the same
  `output.csv` because extraction results are cached in the repository.
