"""Buy-or-Wait agent entry point.

Run:
  python code/main.py                    # predict dataset/requests.csv -> repo-root output.csv
  python code/main.py --samples          # run the 25 solved samples instead (calibration)

Pipeline: load dataset -> resolve blank amounts (image extraction cache) ->
deterministic 90-day simulation -> decision layer -> validate gates -> write CSV.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from data import Dataset, sample_requests
from decide import decide
from forecast import Simulator
from money import D
from validate import validate_row


def _with_amount(e, override):
    if e.amount is None and e.event_id in override:
        amt, cur = override[e.event_id]
        return dataclasses.replace(e, amount=amt, currency=cur)
    return e


def build_rows(ds: Dataset, cfg: Config, requests, amounts_override=None):
    sim = Simulator(ds, cfg)
    rows = []
    for req in requests:
        profile = ds.profiles[req.user_id]
        events = ds.events_by_user.get(req.user_id, [])
        msgs = ds.messages_by_user.get(req.user_id, [])
        if amounts_override:
            events = [_with_amount(e, amounts_override) for e in events]
        row = decide(req, profile, events, msgs, sim)
        problems = validate_row(row, req, profile, events)
        if problems:
            row["_problems"] = problems
        rows.append(row)
    return rows


def load_image_amounts() -> dict:
    cache = ROOT / "code" / "extraction_cache" / "image_amounts.csv"
    out = {}
    if cache.exists():
        with open(cache, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["event_id"]] = (D(r["amount"]), r["currency"])
    return out


def write_output(rows, path: Path):
    cols = ["request_id", "amount_safe_to_pay", "affordability_status",
            "recommended_payment_method", "payment_plan", "earliest_date_for_full_payment",
            "spending_changes_needed", "decision_explanation"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", help="run the 25 solved samples")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = Config()
    ds = Dataset.load()
    override = load_image_amounts()

    reqs = sample_requests(ds) if args.samples else ds.requests
    rows = build_rows(ds, cfg, reqs, override or None)

    problems = [r for r in rows if "_problems" in r]
    for r in problems:
        print(f"VALIDATION {r['request_id']}: {r['_problems']}", file=sys.stderr)

    out = Path(args.out) if args.out else (ROOT / "output.csv")
    write_output(rows, out)
    print(f"wrote {out} ({len(rows)} rows, {len(problems)} validation problems)")


if __name__ == "__main__":
    main()
