"""Deterministic 90-day cash-flow simulator and the safe-amount / earliest-date solvers.

Model
-----
Day 0 is the request date. The daily balance trajectory starts from the profile's
current_available_balance and adds every cash flow on its cash date:

  + projected recurring income (salary streams + message amendments)
  + scheduled/pending confirmed credits (e.g. salary rows)
  - pending debits (reserved), scheduled debits
  - projected recurring expenses (fixed and variable series)
  - foreign-currency flows converted at the flow's settlement-date rate

A payment of X on day d keeps the trajectory safe iff
  min(balance[t] for t in [d, horizon]) - X >= minimum_balance_to_keep.

amount_safe_to_pay      = clamp(min(balance) - min_balance, 0, requested)   (day-0 payment)
earliest_date_for_full  = first day d with suffix_min[d] >= min_balance + requested
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from money import D, ZERO, q2
from config import Config
from income import parse_effects, build_income_streams, project_income
import recurring as rec_mod


@dataclass
class Forecast:
    bal: list[Decimal]                 # balance at end of each day, index 0 = request_date
    suffix_min: list[Decimal]          # min(bal[t] for t in [i, n))
    min_balance_floor: Decimal


class Simulator:
    def __init__(self, ds, cfg: Config):
        self.ds = ds
        self.cfg = cfg

    def _home(self, e, home: str) -> Decimal:
        if e.currency == home:
            return e.amount
        return self.ds.fx.convert(e.amount, e.currency, home, e.cash_date)

    def build_flows(self, req, profile, events, msgs, stop_events=(), reduce_to=()) -> dict:
        cfg = self.cfg
        fx = self.ds.fx
        home = profile.home_currency
        start = req.request_date
        end = start + timedelta(days=cfg.horizon_days - 1)
        eff = parse_effects(msgs or [], start)
        flows: dict[date, Decimal] = {}

        def add(d: date, amt: Decimal):
            if amt != 0:
                flows[d] = flows.get(d, ZERO) + amt

        # ---- one-time future events (duplicates guarded below)
        retried = eff.failed_debit_retry
        candidates: list[tuple[date, Decimal, object]] = []
        for e in events:
            if e.direction == "non_cash":
                continue
            cd = e.event_date if cfg.flow_date_mode == "event_date" else e.cash_date
            if cd is None or not (start <= cd <= end):
                continue
            if e.amount is None:
                continue
            if e.direction == "credit":
                if e.status == "pending":
                    continue  # never count pending credits
                if e.status in ("cancelled", "failed", "unrealized"):
                    continue
                if e.event_type == "income":
                    add(cd, self._home(e, home))
                continue
            # debits
            if e.status in ("cancelled", "unrealized"):
                continue
            if e.status == "failed" and e.event_id not in retried:
                continue
            if e.status == "settled" and cd <= start:
                continue  # already in the balance
            if e.status == "pending" and (not cfg.include_pending_debits):
                continue
            if e.status == "scheduled" and (not cfg.include_scheduled_debits):
                continue
            candidates.append((cd, self._home(e, home), e))

        # ignore duplicate records: same (category, amount) within 3 days
        kept: list[tuple[date, Decimal, object]] = []
        for cd, amt, e in sorted(candidates, key=lambda x: (x[0], x[2].event_id)):
            dup = False
            for kd, kamt, _ke in kept:
                if _ke.category == e.category and kamt == amt \
                        and abs((cd - kd).days) <= 3:
                    dup = True
                    break
            if not dup:
                kept.append((cd, amt, e))
        for cd, amt, e in kept:
            add(cd, -amt)

        # ---- recurring expenses
        series = rec_mod.build_series(req.user_id, events, home, fx, start, cfg)
        stop_ids = set(stop_events)
        reduce_map = dict(reduce_to)
        for s in series:
            if s.event_id in stop_ids:
                continue
            for d, amt, eid in rec_mod.project_series(s, start, end, cfg):
                if eid in stop_ids:
                    continue
                if eid in reduce_map:
                    amt = min(amt, reduce_map[eid])
                if eff.rent_increase_pct is not None and s.category == "rent":
                    amt = amt * (1 + eff.rent_increase_pct)
                add(d, -amt)

        # ---- income
        streams, eff2 = build_income_streams(
            req.user_id, events, msgs or [], home, fx, start, cfg)
        for d, amt in project_income(streams, eff2.one_time_credits, home, fx, start, end, cfg):
            add(d, amt)

        return flows

    def trajectory(self, req, profile, events, msgs, stop_events=(), reduce_to=()) -> Forecast:
        cfg = self.cfg
        flows = self.build_flows(req, profile, events, msgs, stop_events, reduce_to)
        n = cfg.horizon_days
        start = req.request_date
        bal = [profile.balance + flows.get(start, ZERO)] + [ZERO] * n
        for i in range(1, n + 1):
            bal[i] = bal[i - 1] + flows.get(start + timedelta(days=i), ZERO)
        suffix = [ZERO] * (n + 1)
        suffix[n] = bal[n]
        for i in range(n - 1, -1, -1):
            suffix[i] = bal[i] if bal[i] < suffix[i + 1] else suffix[i + 1]
        return Forecast(bal, suffix, profile.min_balance)

    # ------------------------------------------------------------------ solvers

    def amount_safe(self, req, profile, events, msgs) -> Decimal:
        f = self.trajectory(req, profile, events, msgs)
        headroom = f.suffix_min[0] - f.min_balance_floor
        if headroom < ZERO:
            return ZERO
        return min(headroom, req.requested_amount)

    def earliest_full_date(self, req, profile, events, msgs) -> date | None:
        f = self.trajectory(req, profile, events, msgs)
        need = f.min_balance_floor + req.requested_amount
        for i in range(len(f.bal)):
            if f.suffix_min[i] >= need:
                return req.request_date + timedelta(days=i)
        return None

    def plan_safe(self, req, profile, events, msgs, schedule,
                  stop_events=(), reduce_to=()) -> bool:
        """Check a payment schedule (plus optional spending changes) keeps min balance."""
        f = self.trajectory(req, profile, events, msgs, stop_events, reduce_to)
        start = req.request_date
        n = len(f.bal)
        deltas: dict[int, Decimal] = {}
        for d, amt in schedule:
            i = (d - start).days
            if 0 <= i < n:
                deltas[i] = deltas.get(i, ZERO) - amt
        run = ZERO
        for i in range(n):
            run += deltas.get(i, ZERO)
            if f.bal[i] + run < f.min_balance_floor:
                return False
        return True

    # ------------------------------------------------------- spending changes

    def find_changes(self, req, profile, events, msgs, schedule=None):
        """Find stop/reduce changes (<=3) so the target plan stays above min balance.

        Target plan = full payment today, or the supplied installment schedule.
        Every returned candidate is verified with plan_safe before being returned.
        Returns (changes, amounts_by_event_id).
        """
        cfg = self.cfg
        home = profile.home_currency
        start = req.request_date
        end = start + timedelta(days=cfg.horizon_days - 1)
        target = schedule if schedule is not None else [(start, req.requested_amount)]

        # trajectory with the target schedule applied
        f = self.trajectory(req, profile, events, msgs)
        n = len(f.bal)
        bal = list(f.bal)
        for d, amt in target:
            i = (d - start).days
            if 0 <= i < n:
                bal[i] -= amt
        trough = min(bal)
        deficit = f.min_balance_floor - trough
        if deficit <= 0:
            return [], {}
        trough_idx = min(range(n), key=lambda i: bal[i])

        series = rec_mod.build_series(req.user_id, events, home, self.ds.fx, start, cfg)

        def lift_before_trough(s):
            total = ZERO
            for d, amt, _eid in rec_mod.project_series(s, start, end, cfg):
                if (d - start).days <= trough_idx:
                    total += amt
            return total

        stops, reduces = [], []
        for s in series:
            if s.category in set(profile.protected):
                continue  # protected expenses are never changed
            amt = s.projected_amount(cfg)
            if amt <= 0:
                continue
            if s.flexibility in ("stoppable", "reducible_or_stoppable") \
                    and s.category in profile.willing_stop:
                stops.append((amt, lift_before_trough(s), s))
            if s.flexibility in ("reducible", "reducible_or_stoppable") \
                    and s.category in profile.willing_reduce:
                floor = s.min_allowed if s.min_allowed is not None else ZERO
                if amt - floor > 0:
                    reduces.append((amt, floor, lift_before_trough(s), s))

        stops.sort(key=lambda x: (x[0], x[2].event_id))
        reduces.sort(key=lambda x: (x[0] - x[1], x[3].event_id))

        def as_changes(cands):
            changes, stop_ids, reduce_map = [], [], {}
            for c in cands:
                if c[0] == "stop":
                    changes.append(("stop", c[1]))
                    stop_ids.append(c[1].event_id)
                else:
                    changes.append(("reduce_to", c[1], c[2]))
                    reduce_map[c[1].event_id] = c[2]
            return changes, stop_ids, reduce_map

        def try_candidate(cands):
            changes, stop_ids, reduce_map = as_changes(cands)
            if self.plan_safe(req, profile, events, msgs, target, stop_ids, reduce_map):
                amounts = {}
                for c in cands:
                    if c[0] == "stop":
                        amounts[c[1].event_id] = c[1].projected_amount(cfg)
                    else:
                        amounts[c[1].event_id] = c[2]
                return changes, amounts
            return None

        # ordered smallest-sacrifice-first enumeration, up to three changes
        trials = []
        for amt, lift, s in stops:
            trials.append([("stop", s)])
        for amt, floor, lift, s in reduces:
            if amt - deficit >= floor:
                trials.append([("reduce_to", s, amt - deficit)])
        for i, (_, ls, ss) in enumerate(stops):
            for j, (_, _fl, lr, sr) in enumerate(reduces):
                if ss.event_id == sr.event_id:
                    continue
                remaining = deficit - ls
                floor_r = sr.min_allowed if sr.min_allowed is not None else ZERO
                if remaining <= 0:
                    trials.append([("stop", ss)])
                elif lr >= remaining and sr.projected_amount(cfg) - remaining >= floor_r:
                    trials.append([("stop", ss), ("reduce_to", sr, sr.projected_amount(cfg) - remaining)])
        for i in range(len(stops)):
            for j in range(i + 1, len(stops)):
                a, b = stops[i], stops[j]
                if a[2].event_id != b[2].event_id:
                    trials.append([("stop", a[2]), ("stop", b[2])])
        for i in range(len(stops)):
            for j in range(len(stops)):
                for k in range(len(reduces)):
                    a, b, r = stops[i], stops[j], reduces[k]
                    if len({a[2].event_id, b[2].event_id, r[3].event_id}) < 3:
                        continue
                    if a[1] + b[1] >= deficit:
                        trials.append([("stop", a[2]), ("stop", b[2])])
                    else:
                        remaining = deficit - a[1] - b[1]
                        floor = r[1]
                        if r[2] >= remaining and r[0] - remaining >= floor:
                            trials.append([("stop", a[2]), ("stop", b[2]),
                                           ("reduce_to", r[3], r[0] - remaining)])
        for i in range(len(stops)):
            for j in range(len(reduces)):
                for k in range(j + 1, len(reduces)):
                    st, r1, r2 = stops[i], reduces[j], reduces[k]
                    if len({st[2].event_id, r1[3].event_id, r2[3].event_id}) < 3:
                        continue
                    remaining = deficit - st[1]
                    if remaining <= 0:
                        trials.append([("stop", st[2])])
                        continue
                    taken = 0
                    cuts = []
                    ok = True
                    for r in (r1, r2):
                        need = remaining - taken
                        cut = min(r[0] - r[1], max(need, ZERO))
                        if need > 0 and cut <= 0:
                            ok = False
                            break
                        cuts.append(("reduce_to", r[3], r[0] - cut))
                        taken += cut
                    if ok and taken >= remaining:
                        trials.append([("stop", st[2])] + cuts)

        for cands in trials:
            res = try_candidate(cands)
            if res is not None:
                return res
        return [], {}
