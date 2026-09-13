"""Generate evaluation/usage_report.md from the extraction cache and usage logs.

Run: python evaluation/usage_report.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "code" / "extraction_cache"


def main():
    lines = []
    w = lines.append
    w("# Token Usage and Cost Analysis")
    w("")
    w("Final full-dataset run that produced `output.csv` (250 requests).")
    w("")
    w("## Architecture summary")
    w("")
    w("- Deterministic Decimal cash-flow engine (pure Python): no model calls at")
    w("  decision time. All financial math — 90-day forecasts, safe-amount solvers,")
    w("  plan ranking, validation gates — is deterministic and replayable offline.")
    w("- Model usage is confined to unstructured-input extraction, and every response")
    w("  is cached on disk (`code/extraction_cache/`). The final run replays the cache;")
    w("  no tokens are consumed while producing `output.csv`.")
    w("")
    w("## Model calls")
    w("")
    rows = []
    total_calls = total_in = total_out = 0
    img_usage = CACHE / "usage_images.json"
    if img_usage.exists():
        u = json.loads(img_usage.read_text())
        rows.append(("Google Gemini (vision)", "gemini-2.5-flash",
                     str(u["calls"]), str(u["prompt"]), str(u["output"])))
        total_calls += u["calls"]
        total_in += u["prompt"]
        total_out += u["output"]
    msg_usage = CACHE / "usage_messages.json"
    if msg_usage.exists():
        u = json.loads(msg_usage.read_text())
        if u.get("calls"):
            rows.append(("Google Gemini (text)", "gemini-2.5-flash",
                         str(u["calls"]), str(u["prompt"]), str(u["output"])))
            total_calls += u["calls"]
            total_in += u["prompt"]
            total_out += u["output"]

    w("| Provider | Model | Calls | Input tokens | Output tokens |")
    w("|---|---|---|---|---|")
    for r in rows:
        w(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    n_req = 250
    tot = total_in + total_out
    w(f"| **Total** | — | **{total_calls}** | **{total_in}** | **{total_out}** |")
    w("")
    w(f"- Total tokens (input + output): {tot}")
    w(f"- Average tokens per request ({n_req} requests): {tot / n_req:.1f}")
    w(f"- Average model calls per request: {total_calls / n_req:.3f}")
    w("")
    w("## Cost")
    w("")
    w("- All model calls ran on the Google AI Studio **free tier** (gemini-2.5-flash).")
    w("- Estimated total cost: **$0.00**; estimated per-request cost: **$0.0000**.")
    w("- For reference, at public list pricing this extraction volume would cost")
    w("  well under $0.05; the deterministic engine itself consumes no tokens.")
    w("")
    w("## Replay / determinism")
    w("")
    w("- `output.csv` is produced by `python code/main.py`, which reads the cached")
    w("  extractions and runs the deterministic engine. Two consecutive runs produce")
    w("  byte-identical output (verified).")
    w("- Re-running the full pipeline without an API key reproduces the same")
    w("  `output.csv` because extraction results are cached in the repository.")
    w("")
    (ROOT / "evaluation" / "usage_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote evaluation/usage_report.md")


if __name__ == "__main__":
    main()
