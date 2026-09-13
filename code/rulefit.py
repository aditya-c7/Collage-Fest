"""Rule-fit analysis: for each sample, find which series amount rule explains the
generator's trough exactly. Prints per-series candidate amounts under each rule.

Run: python code/rulefit.py [request_id ...]
"""
from __future__ import annotations

import csv
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from data import Dataset, sample_requests
from forecast import Simulator
from money import ZERO
import recurring as rec_mod


def rules(amts):
    return {
        "last": amts[-1],
        "mean": sum(amts) / len(amts),
        "max3": max(amts[-3:]),
        "min3": min(amts[-3:]),
        "min": min(amts),
        "max": max(amts),
    }


def main():
    cfg = Config(var_amount_rule="min", frequent_var_mode="asis", income_var_rule="mode",
                 month_anchor_mode="dom", day0_flows=True)
    ds = Dataset.load()
    sim = Simulator(ds, cfg)
    with open(ROOT / "dataset" / "sample_requests.csv", newline="", encoding="utf-8") as f:
        gold = {r["request_id"]: r for r in csv.DictReader(f)}
    want = set(sys.argv[1:]) or None

    for req in sample_requests(ds):
        if want and req.request_id not in want:
            continue
        profile = ds.profiles[req.user_id]
        events = ds.events_by_user.get(req.user_id, [])
        msgs = ds.messages_by_user.get(req.user_id, [])
        g = gold[req.request_id]
        gold_trough = profile.min_balance + Decimal(g["amount_safe_to_pay"])
        f = sim.trajectory(req, profile, events, msgs)
        my_trough = f.suffix_min[0]
        if abs(my_trough - gold_trough) <= Decimal("0.005"):
            continue
        start = req.request_date
        end = start + timedelta(days=cfg.horizon_days - 1)
        trough_i = min(range(len(f.bal)), key=lambda i: f.bal[i])
        print("=" * 100)
        print(f"{req.request_id} {req.user_id} home={profile.home_currency} "
              f"my_trough={my_trough} @day{trough_i} gold_trough={gold_trough} "
              f"delta={my_trough - gold_trough} (pos => generator spent LESS before trough)")
        series = rec_mod.build_series(req.user_id, events, profile.home_currency, ds.fx, start, cfg)
        for s in sorted(series, key=lambda x: x.category):
            amts = [o.amount for o in s.occurrences]
            pre = [(d, a) for d, a, _ in rec_mod.project_series(s, start, end, cfg)
                   if (d - start).days <= trough_i]
            if not pre:
                continue
            r = rules(amts)
            n_pre = len(pre)
            need_per = (my_trough - gold_trough) / Decimal(n_pre)
            print(f"  {s.category:<20} kind={s.kind:<13} n_pre={n_pre} used={s.projected_amount(cfg):>14}")
            print(f"     rules: " + "  ".join(f"{k}={v:.2f}" for k, v in r.items()))
            print(f"     need_per_occ={need_perOcc_format(need_per)}  dates_pre={[str(d) for d, _ in pre]}")
        # income check
        from income import build_income_streams, project_income
        streams, eff = build_income_streams(req.user_id, events, msgs or [],
                                            profile.home_currency, ds.fx, start, cfg)
        inc = project_income(streams, eff.one_time_credits, profile.home_currency,
                             ds.fx, start, end, cfg)
        print(f"  income pre-trough: {[(str(d), str(a)) for d, a in sorted(inc) if (d - start).days <= trough_i]}")
        print(f"  income all: {len(inc)} occurrences; gold earliest={g['earliest_date_for_full_payment']}")


def needPerOcc_format(x):
    return f"{x:.4f}"


need_perOcc = needPerOcc_format


def need_perOcc_format(x):
    return f"{x:.4f}"


if __name__ == "__main__":
    main()
