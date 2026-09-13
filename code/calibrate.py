"""Grid-search the projection knobs against the 25 solved samples.

Scores: exact amount matches, earliest-date matches, status matches, full-row match.
Run: python code/calibrate.py
"""
from __future__ import annotations

import csv
import itertools
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from data import Dataset, sample_requests
from decide import decide
from forecast import Simulator
from main import load_image_amounts
import dataclasses

FIELDS_AMOUNT = "amount_safe_to_pay"
FIELDS = ["affordability_status", "recommended_payment_method", "payment_plan",
          "earliest_date_for_full_payment", "spending_changes_needed"]


def load_gold():
    with open(ROOT / "dataset" / "sample_requests.csv", newline="", encoding="utf-8") as f:
        return {r["request_id"]: r for r in csv.DictReader(f)}


def score(ds, gold, combos, override):
    sim = Simulator(ds, combos)
    reqs = sample_requests(ds)
    amount_ok = status_ok = earliest_ok = full = 0
    n = len(reqs)
    for req in reqs:
        profile = ds.profiles[req.user_id]
        events = ds.events_by_user.get(req.user_id, [])
        if override:
            events = [dataclasses.replace(e, amount=override[e.event_id][0],
                                          currency=override[e.event_id][1])
                      if e.amount is None and e.event_id in override else e
                      for e in events]
        msgs = ds.messages_by_user.get(req.user_id, [])
        row = decide(req, profile, events, msgs, sim)
        g = gold[req.request_id]
        try:
            amt_ok = abs(Decimal(row["amount_safe_to_pay"]) - Decimal(g["amount_safe_to_pay"])) <= Decimal("0.005")
        except Exception:
            amt_ok = False
        ed_ok = row["earliest_date_for_full_payment"] == g["earliest_date_for_full_payment"]
        st_ok = row["affordability_status"] == g["affordability_status"]
        others = all(row[k] == g[k] for k in FIELDS if k != "earliest_date_for_full_payment")
        amount_ok += amt_ok
        status_ok += st_ok
        earliest_ok += ed_ok
        full += amt_ok and ed_ok and st_ok and others
    return amount_ok, status_ok, earliest_ok, full, n


def main():
    ds = Dataset.load()
    gold = load_gold()
    override = load_image_amounts()
    best = None
    grid = list(itertools.product(
        ["last", "mean", "mean3", "max3", "min3", "min"],  # var_amount_rule (frequent)
        ["last", "mean", "mean3", "max3", "min3", "min", ""],  # monthly_var_rule
    ))
    print(f"testing {len(grid)} combos on 25 samples...")
    for var_rule, mv_rule in grid:
        cfg = Config(var_amount_rule=var_rule, monthly_var_rule=mv_rule,
                     frequent_var_mode="asis", income_var_rule="mode")
        a, s, e, f, n = score(ds, gold, cfg, override)
        line = f"freq={var_rule:<6} monthly={mv_rule or '-':<6} -> amt={a} status={s} earliest={e} FULL={f}/{n}"
        print(line, flush=True)
        key = (f, a, e, s)
        if best is None or key > best[0]:
            best = (key, cfg, line)
    print("\nBEST:", best[1])
    print(best[2])


if __name__ == "__main__":
    main()
