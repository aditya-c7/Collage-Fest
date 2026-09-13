"""Per-sample flow ledger diagnostic: where does my trough differ from the gold one?

Run: python code/diagnose.py [request_id ...]
"""
from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from data import Dataset, sample_requests
from forecast import Simulator
from income import build_income_streams, project_income
from main import load_image_amounts
import dataclasses
import recurring as rec_mod


def with_amounts(events, override):
    if not override:
        return events
    out = []
    for e in events:
        if e.amount is None and e.event_id in override:
            amt, cur = override[e.event_id]
            out.append(dataclasses.replace(e, amount=amt, currency=cur))
        else:
            out.append(e)
    return out


def flows_ledger(sim, req, profile, events, msgs, gold_safe):
    fx = sim.ds.fx
    home = profile.home_currency
    cfg = sim.cfg
    start = req.request_date
    end = start + timedelta(days=cfg.horizon_days - 1)
    flows = sim.build_flows(req, profile, events, msgs)

    # my trajectory
    bal = [profile.balance + flows.get(start, ZERO)] + [ZERO] * cfg.horizon_days
    for i in range(1, cfg.horizon_days + 1):
        bal[i] = bal[i - 1] + flows.get(start + timedelta(days=i), ZERO)
    trough_i = min(range(len(bal)), key=lambda i: bal[i])
    my_trough = bal[trough_i]
    gold_trough = profile.min_balance + gold_safe

    print(f"\n### {req.request_id} {req.user_id} bal={profile.balance} min={profile.min_balance}")
    print(f"  my_trough={my_trough} on day {trough_i} ({start + timedelta(days=trough_i)})"
          f"  gold_trough={gold_trough}  delta={my_trough - gold_trough}")
    print(f"  flows (nonzero) around window:")
    for d in sorted(flows):
        if flows[d] != 0:
            print(f"    {(d - start).days:>3} {d} {flows[d]:>18}")
    # series summary
    series = rec_mod.build_series(req.user_id, events, home, fx, start, cfg)
    print("  series:")
    for s in sorted(series, key=lambda x: x.category):
        proj = rec_mod.project_series(s, start, end, cfg)
        amt = s.projected_amount(cfg)
        print(f"    {s.category:<22} {s.kind:<13} anchor={s.day_anchor:<3} amt={amt:>12} "
              f"flex={s.flexibility:<22} min_allowed={s.min_allowed} eid={s.event_id} "
              f"n_proj={len(proj)}")
    streams, eff = build_income_streams(req.user_id, events, msgs or [], home, fx, start, cfg)
    print("  income streams:")
    for s in streams:
        print(f"    {s.category:<10} {s.description[:40]:<42} payday={s.payday} amt={s.amount} "
              f"raise={s.raise_from}/{s.raise_amount} next_ovr={s.next_override} "
              f"stop_after={s.stop_after} start_from={s.start_from}")
    print(f"  one-time credits: {eff.one_time_credits}")
    print(f"  effects: stop={eff.stop} date_move={eff.date_move} rent%={eff.rent_increase_pct} "
          f"failed_retry={eff.failed_debit_retry}")


from money import ZERO

def main():
    cfg = Config()
    ds = Dataset.load()
    sim = Simulator(ds, cfg)
    with open(ROOT / "dataset" / "sample_requests.csv", newline="", encoding="utf-8") as f:
        gold = {r["request_id"]: r for r in csv.DictReader(f)}
    want = set(sys.argv[1:])
    override = load_image_amounts()
    for req in sample_requests(ds):
        if want and req.request_id not in want:
            continue
        profile = ds.profiles[req.user_id]
        events = with_amounts(ds.events_by_user.get(req.user_id, []), override)
        msgs = ds.messages_by_user.get(req.user_id, [])
        g = gold[req.request_id]
        flows_ledger(sim, req, profile, events, msgs, Decimal(g["amount_safe_to_pay"]))


if __name__ == "__main__":
    main()
