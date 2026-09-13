"""Exact subset-sum solver: for each sample, find the per-series amount-rule
assignment whose projected pre-trough spend matches the generator's trough to
the cent. Reveals the generator's actual projection rule.

Run: python code/solver.py [request_id ...]
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

RULES = ["last", "mean", "max3", "min3", "min", "max"]


def rule_amount(amts, rule):
    if rule == "last":
        return amts[-1]
    if rule == "mean":
        return sum(amts) / len(amts)
    if rule == "max3":
        return max(amts[-3:])
    if rule == "min3":
        return min(amts[-3:])
    if rule == "min":
        return min(amts)
    if rule == "max":
        return max(amts)
    raise ValueError(rule)


def main():
    cfg = Config(var_amount_rule="max3", frequent_var_mode="asis", income_var_rule="mode",
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
            print(f"{req.request_id}: EXACT with max3/asis/mode")
            continue
        start = req.request_date
        end = start + timedelta(days=cfg.horizon_days - 1)
        trough_i = min(range(len(f.bal)), key=lambda i: f.bal[i])
        # needed: gold_trough - my_trough; positive => generator spent less
        needed = (gold_trough - my_trough) * 100  # cents
        series = rec_mod.build_series(req.user_id, events, profile.home_currency,
                                      ds.fx, start, cfg)
        # options per series: (name, delta_cents) — switching amount by delta
        opts = []
        for s in sorted(series, key=lambda x: x.category):
            amts = [o.amount for o in s.occurrences]
            pre = [(d, a) for d, a, _ in rec_mod.project_series(s, start, end, cfg)
                   if (d - start).days <= trough_i]
            if not pre:
                continue
            n_pre = len(pre)
            base = rule_amount(amts, "max3")
            choices = []
            for r in RULES:
                d_cents = int(((rule_amount(amts, r) - base) * n_pre * 100).to_integral_value())
                choices.append((f"{s.category}:{r}", d_cents))
            choices.append((f"{s.category}:DROP", int((-base * n_pre * 100).to_integral_value())))
            opts.append(choices)

        # subset-sum DP to hit `needed` exactly (cents as int)
        target = int(needed.to_integral_value())
        states = {0: []}
        for choices in opts:
            nxt = {}
            for total, combo in states.items():
                for name, d in choices:
                    t2 = total + d
                    if t2 not in nxt:
                        nxt[t2] = combo + [name]
            # prune: keep states within plausible range
            states = {t: c for t, c in nxt.items() if -10 ** 9 < t < 10 ** 10}
            # cap combinatorial blowup
            if len(states) > 400000:
                states = dict(sorted(states.items())[:400000])
        hits = states.get(target)
        if hits:
            print(f"{req.request_id}: EXACT combo -> {hits}")
        else:
            # nearest
            best_t = min(states, key=lambda t: abs(t - target)) if states else None
            print(f"{req.request_id}: no exact combo (target {target} cents); "
                  f"nearest {best_t} via {states.get(best_t)}")


if __name__ == "__main__":
    main()
