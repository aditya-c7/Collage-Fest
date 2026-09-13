"""Phase 0 profiling: shape, nulls, distinct values, and ranges for every dataset CSV.

Run: python code/profile_data.py
"""
import csv
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"

FILES = [
    "requests.csv",
    "sample_requests.csv",
    "financial_profiles.csv",
    "financial_events.csv",
    "request_payment_options.csv",
    "exchange_rates.csv",
    "messages.csv",
    "images.csv",
    "output.csv",
]


def load(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def profile(name, rows, max_distinct=25):
    print(f"\n{'=' * 70}\n{name}: {len(rows)} rows")
    if not rows:
        return
    cols = list(rows[0].keys())
    for col in cols:
        vals = [r[col] for r in rows]
        blanks = sum(1 for v in vals if v is None or v.strip() == "")
        distinct = Counter(vals)
        n_distinct = len(distinct)
        if n_distinct <= max_distinct:
            top = ", ".join(f"{k!r}x{c}" for k, c in distinct.most_common(max_distinct))
            print(f"  {col}: blanks={blanks} distinct={n_distinct} [{top}]")
        else:
            sample = distinct.most_common(3)
            print(f"  {col}: blanks={blanks} distinct={n_distinct} (top: {sample})")


def main():
    for name in FILES:
        path = DATA / name
        if not path.exists():
            print(f"\n{name}: MISSING")
            continue
        profile(name, load(name))

    media = DATA / "media" / "images"
    pngs = sorted(p.name for p in media.glob("*.png")) if media.exists() else []
    print(f"\nmedia/images: {len(pngs)} files: {pngs}")

    # images.csv vs media cross-check
    img_rows = load("images.csv")
    linked = {r["image_id"] for r in img_rows}
    on_disk = {p[:-4] for p in pngs}
    print(f"  images.csv ids not on disk: {sorted(linked - on_disk)}")
    print(f"  files on disk not in images.csv: {sorted(on_disk - linked)}")

    # event ids referenced by images
    ev_ids = {r["related_event_id"] for r in img_rows}
    print(f"  images reference {len(ev_ids)} distinct events: {sorted(ev_ids)[:20]}...")


if __name__ == "__main__":
    sys.exit(main())
