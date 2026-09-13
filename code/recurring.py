"""Recurring expense detection and projection (parameterized for calibration).

Groups settled history by (user, category), classifies cadence, and projects
future occurrences over the forecast window. Strategy knobs live in Config so
the calibration loop can fit them to the samples without code changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from money import D, ZERO, month_shift


@dataclass
class Occurrence:
    dt: date
    amount: Decimal


@dataclass
class Series:
    """One recurring expense stream."""
    user_id: str
    category: str
    kind: str            # "monthly_fixed" | "monthly_var" | "frequent_var"
    day_anchor: int      # day of month for monthly series
    occurrences: list[Occurrence]
    flexibility: str     # from most recent occurrence
    min_allowed: Decimal | None
    event_id: str        # id of most recent event (for spending changes)
    description: str = ""  # most recent event description (for explanations)

    def projected_amount(self, cfg) -> Decimal:
        amts = [o.amount for o in self.occurrences]
        if self.kind == "monthly_fixed":
            return amts[-1]
        if self.kind == "monthly_var" and getattr(cfg, "monthly_var_rule", ""):
            return _rule_amount(amts, cfg.monthly_var_rule)
        if cfg.var_amount_rule == "last":
            return amts[-1]
        if cfg.var_amount_rule == "mean":
            return sum(amts) / len(amts)
        if cfg.var_amount_rule == "max3":
            return max(amts[-3:])
        if cfg.var_amount_rule == "min3":
            return min(amts[-3:])
        if cfg.var_amount_rule == "mean3":
            return sum(amts[-3:]) / 3
        if cfg.var_amount_rule == "min":
            return min(amts)
        return amts[-1]

    def monthly_rate(self, cfg) -> Decimal:
        """Average home-currency outflow per month over the history window."""
        span_days = (self.occurrences[-1].dt - self.occurrences[0].dt).days or 1
        months = Decimal(max(span_days, 30)) / Decimal(30)
        return sum(o.amount for o in self.occurrences) / months


def _rule_amount(amts, rule):
    if rule == "last":
        return amts[-1]
    if rule == "mean":
        return sum(amts) / len(amts)
    if rule == "mean3":
        return sum(amts[-3:]) / 3
    if rule == "max3":
        return max(amts[-3:])
    if rule == "min3":
        return min(amts[-3:])
    if rule == "min":
        return min(amts)
    return amts[-1]


def classify(occ: list[Occurrence], cfg) -> str:
    """Classify cadence from the interval pattern."""
    if len(occ) < cfg.min_occurrences:
        return "none"
    intervals = [(b.dt - a.dt).days for a, b in zip(occ, occ[1:])]
    med = sorted(intervals)[len(intervals) // 2]
    if med >= 25:
        return "monthly_fixed" if _is_fixed(occ, cfg) else "monthly_var"
    if med >= cfg.frequent_min_gap:
        return "frequent_var"
    return "frequent_var"


def _is_fixed(occ: list[Occurrence], cfg) -> bool:
    amts = [o.amount for o in occ]
    return max(amts) == min(amts)


def build_series(user_id: str, events: list, home: str, fx, request_date: date,
                 cfg) -> list[Series]:
    """Build recurring expense series from settled debit history before request_date.

    Investment contributions (event_type=investment_purchase) are deliberately
    NOT projected as recurring: in this dataset they are one-time purchases per
    user (29 rows / 275 users), already reflected in the balance; any future
    scheduled investment debit flows through the one-time-event path instead.
    """
    lookback_start = request_date - timedelta(days=cfg.history_days)
    groups: dict[str, list] = {}
    for e in events:
        if e.direction != "debit" or e.status != "settled":
            continue
        if e.amount is None or e.amount == 0:
            continue
        if e.event_type not in ("expense", "subscription", "debt_payment"):
            continue
        cd = e.cash_date
        if not (lookback_start <= cd < request_date):
            continue
        amt = e.amount if e.currency == home else fx.convert(e.amount, e.currency, home, cd)
        groups.setdefault(e.category, []).append((cd, amt, e))

    series = []
    for cat, items in groups.items():
        items.sort(key=lambda x: x[0])
        occ = [Occurrence(d, a) for d, a, _ in items]
        kind = classify(occ, cfg)
        if kind == "none":
            continue
        last = items[-1][2]
        # monthly anchor: day-of-month of the most recent occurrence
        series.append(Series(
            user_id=user_id,
            category=cat,
            kind=kind,
            day_anchor=occ[-1].dt.day,
            occurrences=occ,
            flexibility=last.flexibility,
            min_allowed=last.minimum_allowed_amount,
            event_id=last.event_id,
            description=last.description,
        ))
    return series


def project_series(s: Series, start: date, end: date, cfg) -> list[tuple[date, Decimal, str]]:
    """Project (date, amount, event_id) occurrences in [start, end].

    event_id is the source event for spending-change references.
    """
    out: list[tuple[date, Decimal, str]] = []
    if s.kind in ("monthly_fixed", "monthly_var"):
        amt = s.projected_amount(cfg)
        d = _next_monthly(s, start, cfg)
        while d <= end:
            out.append((d, amt, s.event_id))
            d = _next_monthly(s, d + timedelta(days=1), cfg)
        return out

    # frequent variable series
    if cfg.frequent_var_mode == "drop":
        return out
    if cfg.frequent_var_mode == "monthly":
        amt = s.monthly_rate(cfg)
        d = _next_monthly(s, start, cfg)
        while d <= end:
            out.append((d, amt, s.event_id))
            d = _next_monthly(s, d + timedelta(days=1), cfg)
        return out

    # asis: occurrences at the median gap from the last observed occurrence
    if len(s.occurrences) < 2:
        return out
    gaps = [(b.dt - a.dt).days for a, b in zip(s.occurrences, s.occurrences[1:])]
    gap = max(1, sorted(gaps)[len(gaps) // 2])
    amt = s.projected_amount(cfg)
    d = s.occurrences[-1].dt + timedelta(days=gap)
    while d <= end:
        if d >= start:
            out.append((d, amt, s.event_id))
        d += timedelta(days=gap)
    return out


def _next_monthly(s: Series, start: date, cfg) -> date:
    """First projected monthly occurrence on/after `start` for this series."""
    if cfg.month_anchor_mode == "plus30":
        d = s.occurrences[-1].dt
        while d < start:
            d += timedelta(days=30)
        return d
    anchor = s.day_anchor
    y, m = start.year, start.month
    d = date(y, m, min(anchor, _dim(y, m)))
    if d < start:
        d = month_shift(d, 1)
    return d


def _dim(y: int, m: int) -> int:
    if m == 12:
        return 31
    return (date(y + 1, 1, 1) - date(y, m, 1)).days if m == 12 else (date(y, m % 12 + 1, 1) - date(y, m, 1)).days
