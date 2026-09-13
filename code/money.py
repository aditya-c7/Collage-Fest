"""Money, dates, and FX utilities. All arithmetic is Decimal; no floats anywhere."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
from pathlib import Path

TWO = Decimal("0.01")
ZERO = Decimal("0")


def D(x) -> Decimal:
    if x is None:
        return ZERO
    s = str(x).strip().replace(",", "").strip(".")
    try:
        return Decimal(s) if s else ZERO
    except Exception:
        return ZERO


def q2(x: Decimal, mode=ROUND_HALF_UP) -> Decimal:
    return x.quantize(TWO, rounding=mode)


def fmt_plain(x: Decimal) -> str:
    """Generator-style amount_safe formatting: 2dp, plain notation, strip trailing zeros."""
    s = format(q2(x), "f")  # "f" never emits exponent notation
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt_plan(x: Decimal) -> str:
    """Generator-style plan-amount formatting: integral -> no decimals, else exactly 2dp."""
    x = q2(x)
    if x == x.to_integral_value():
        return str(int(x))
    return f"{x:.2f}"


def fmt_group(x: Decimal) -> str:
    """Comma-grouped amount for explanations: integral -> none, else 2dp."""
    x = q2(x)
    if x == x.to_integral_value():
        return f"{int(x):,}"
    return f"{x:,.2f}"


def fmt_date(d: date) -> str:
    return d.isoformat()


def fmt_date_human(d: date) -> str:
    return f"{d.day} {d.strftime('%B')} {d.year}"


def month_shift(d: date, k: int) -> date:
    """Same day-of-month k months away, clamped to month end (e.g. Jan 31 -> Feb 28)."""
    m = d.month - 1 + k
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, _days_in_month(y, m))
    return date(y, m, day)


def _days_in_month(y: int, m: int) -> int:
    if m == 12:
        return 31
    return (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------- FX

@dataclass(frozen=True)
class Rate:
    rate_date: date
    frm: str
    to: str
    rate: Decimal


class FX:
    """Dated FX with direct -> inverse -> USD-bridge resolution.

    Rates are quoted on the 15th of each month and treated as effective from
    their rate_date until the next rate_date for the same pair (fall-forward).
    """

    def __init__(self, rates: list[Rate]):
        self.by_pair: dict[tuple[str, str], list[Rate]] = {}
        for r in rates:
            self.by_pair.setdefault((r.frm, r.to), []).append(r)
        for lst in self.by_pair.values():
            lst.sort(key=lambda r: r.rate_date)
        self.pairs = set(self.by_pair.keys())
        self.mode = ROUND_HALF_UP

    def _lookup(self, frm: str, to: str, on: date) -> Decimal | None:
        lst = self.by_pair.get((frm, to))
        if not lst:
            return None
        # latest rate_date <= on; if none (on before first rate), use first rate
        chosen = None
        for r in lst:
            if r.rate_date <= on:
                chosen = r
        if chosen is None:
            chosen = lst[0]
        return chosen.rate

    def convert(self, amount: Decimal, frm: str, to: str, on: date) -> Decimal:
        """Convert amount from frm to to using rates effective on `on`.

        Chain: direct -> inverse -> USD bridge. No intermediate rounding;
        the caller rounds once at the point of use.
        """
        if frm == to:
            return amount
        r = self._lookup(frm, to, on)
        if r is not None:
            return amount * r
        r = self._lookup(to, frm, on)
        if r is not None:
            return amount / r
        # USD bridge: frm -> USD -> to (or via EUR if USD not reachable)
        for bridge in ("USD", "EUR"):
            if bridge in (frm, to):
                continue
            r1 = self._lookup(frm, bridge, on)
            if r1 is None:
                r1 = self._lookup(bridge, frm, on)
                if r1 is not None:
                    r1 = 1 / r1
            r2 = self._lookup(bridge, to, on)
            if r2 is None:
                r2 = self._lookup(to, bridge, on)
                if r2 is not None:
                    r2 = 1 / r2
            if r1 is not None and r2 is not None:
                return amount * r1 * r2
        raise ValueError(f"no FX path {frm}->{to} on {on}")


def load_fx(path: Path) -> FX:
    rates = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rates.append(Rate(
                rate_date=date.fromisoformat(row["rate_date"]),
                frm=row["from_currency"],
                to=row["to_currency"],
                rate=D(row["rate"]),
            ))
    return FX(rates)
