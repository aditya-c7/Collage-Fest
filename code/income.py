"""Income modeling: salary streams, message amendments (Tier-0 heuristics), and
confirmed one-time future income (approved invoices, salary confirmations).

All amounts are normalized to the user's home currency at their cash date.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from money import D, ZERO, month_shift
from recurring import Occurrence

MONEY = re.compile(r"([A-Z]{3})\s*([\d][\d.,]*)")
DATES = re.compile(r"(\d{4}-\d{2}-\d{2})")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december",
     "januari", "februari", "maret", "mei", "juni", "juli",
     "agustus", "oktober", "november", "desember"])}
HUMAN_DATES = re.compile(
    r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.I)


def _human_dates(text: str) -> list:
    out = []
    for d, mon, y in HUMAN_DATES.findall(text):
        m = _MONTHS.get(mon.lower())
        if m:
            try:
                out.append(date(int(y), m, int(d)))
            except ValueError:
                pass
    return out
NON_RECURRING_INCOME = re.compile(
    r"commission|bonus|incentive|overtime|allowance|prize|windfall|arrears|refund", re.I)


@dataclass
class IncomeEffects:
    """Message-derived amendments for one user."""
    raise_amount: Decimal | None = None
    raise_currency: str | None = None
    raise_from: date | None = None
    date_move: date | None = None
    stop: bool = False
    resume_date: date | None = None
    resume_amount: Decimal | None = None
    resume_currency: str | None = None
    next_amount: Decimal | None = None
    next_currency: str | None = None
    first_date: date | None = None
    first_amount: Decimal | None = None
    first_currency: str | None = None
    one_time_credits: list = field(default_factory=list)  # (cash_date, amount, currency, label)
    rent_increase_pct: Decimal | None = None
    failed_debit_retry: set = field(default_factory=set)
    remaining_salary: Decimal | None = None   # household-stream ended: surviving salary
    remaining_salary_currency: str | None = None
    arrears_amount: Decimal | None = None     # one-time arrears in the next payroll
    arrears_currency: str | None = None


def parse_effects(messages: list, request_date: date) -> IncomeEffects:
    eff = IncomeEffects()
    for m in messages:
        if m.sent_at.date() > request_date:
            continue
        t = m.text
        tl = t.lower()
        amounts = [(c, D(a.replace(",", ""))) for c, a in MONEY.findall(t)]
        dates = [date.fromisoformat(x) for x in DATES.findall(t)]

        all_dates = dates + _human_dates(t)

        if m.source_type == "employer":
            # next-payroll regular amount (optionally with one-time arrears)
            if re.search(r"regular salary for the next payroll is|gaji rutin .{0,20}untuk penggajian berikutnya adalah", tl):
                if amounts:
                    eff.next_amount = amounts[0][1]
                    eff.next_currency = amounts[0][0]
                arr = re.search(r"(?:arrears adjustment of|tunggakan satu kali sebesar)\s*([A-Z]{3})\s*([\d.,]+)", t)
                if arr:
                    eff.arrears_amount = D(arr.group(2).replace(",", ""))
                    eff.arrears_currency = arr.group(1)
            # household stream ended: surviving salary
            if re.search(r"household employment record has ended|sumber pendapatan kerja rumah tangga telah berakhir", tl)                     and re.search(r"remaining confirmed monthly salary is|sisa gaji bulanan yang dikonfirmasi adalah", tl):
                if amounts:
                    eff.remaining_salary = amounts[0][1]
                    eff.remaining_salary_currency = amounts[0][0]
            # confirmed salary credit with settlement date (EN + ID)
            if re.search(r"salary of .{0,30}is confirmed for|gaji sebesar .{0,30}dikonfirmasi untuk", tl):
                if amounts and all_dates:
                    eff.one_time_credits.append((all_dates[0], amounts[0][1], amounts[0][0],
                                                 "salary_credit_confirmed"))
            if re.search(r"naik menjadi|increased? to|salary (?:is )?(?:now|will be) (?:increased|raised)", tl):
                if amounts:
                    eff.raise_amount = amounts[0][1]
                    eff.raise_currency = amounts[0][0]
                    eff.raise_from = dates[0] if dates else None
            elif re.search(r"reduced to|temporary monthly pay|dikurangi menjadi|gaji bulanan sementara", tl):
                if amounts:
                    eff.next_amount = amounts[0][1]
                    eff.next_currency = amounts[0][0]
            elif re.search(r"gaji pokok yang dikonfirmasi|confirmed base salary", tl):
                if amounts:
                    eff.raise_amount = amounts[0][1]
                    eff.raise_currency = amounts[0][0]
                    eff.raise_from = dates[0] if dates else None
            if re.search(r"now expected on|diharapkan pada|replaces the payroll date", tl):
                if dates:
                    eff.date_move = dates[0]
            if re.search(r"contract has ended|kontrak .* berakhir|no off-season income|no renewal has been confirmed", tl):
                eff.stop = True
            if re.search(r"resumes on|kembali pada", tl):
                if amounts:
                    eff.resume_amount = amounts[0][1]
                    eff.resume_currency = amounts[0][0]
                if dates:
                    eff.resume_date = dates[0]
            if re.search(r"first salary|gaji pertama", tl):
                if amounts:
                    eff.first_amount = amounts[0][1]
                    eff.first_currency = amounts[0][0]
                if dates:
                    eff.first_date = dates[0]

        if m.source_type == "service_provider" and re.search(
                r"approved an invoice payment|menyetujui pembayaran faktur", tl):
            if amounts and dates:
                eff.one_time_credits.append((dates[0], amounts[0][1], amounts[0][0], "approved_invoice"))

        if m.source_type == "financial_service" and re.search(
                r"salary credit for|confirmed a [a-z]{3} [\d.,]+ salary", tl):
            if amounts and all_dates:
                # the credit date follows "for"; prefer a date after the phrase
                eff.one_time_credits.append((all_dates[-1], amounts[-1][1], amounts[-1][0],
                                             "salary_credit"))

        if re.search(r"increases monthly rent by|menaikkan biaya sewa bulanan sebesar", tl):
            pct = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
            if pct:
                eff.rent_increase_pct = D(pct.group(1)) / 100

        if m.related_event_id and re.search(
                r"debit attempt failed|still outstanding|another debit will be attempted", tl):
            eff.failed_debit_retry.add(m.related_event_id)

    return eff


@dataclass
class IncomeStream:
    """A projected recurring income stream (usually salary)."""
    category: str
    description: str
    payday: date
    amount: Decimal                  # base per-occurrence amount (home currency)
    raise_from: date | None = None
    raise_amount: Decimal | None = None
    next_override: Decimal | None = None
    stop_after: date | None = None
    start_from: date | None = None
    source_event: object | None = None


def _mode_amount(amts: list[Decimal]) -> Decimal:
    counts: dict[Decimal, int] = {}
    for a in amts:
        counts[a] = counts.get(a, 0) + 1
    best = max(amts, key=lambda a: (counts[a], amts.index(a)))
    if counts[best] >= 2:
        return best
    return sum(amts) / len(amts)


def build_income_streams(user_id: str, events: list, msgs: list, home: str, fx,
                         request_date: date, cfg):
    """Detect recurring income from settled history + scheduled rows, apply amendments."""
    eff = parse_effects(msgs or [], request_date)
    lookback_start = request_date - timedelta(days=cfg.history_days)

    groups: dict[str, list] = {}
    for e in events:
        if e.direction != "credit" or e.status != "settled":
            continue
        if e.amount is None or e.amount == 0:
            continue
        cd = e.cash_date
        if not (lookback_start <= cd < request_date):
            continue
        amt = e.amount if e.currency == home else fx.convert(e.amount, e.currency, home, cd)
        groups.setdefault(e.description.strip(), []).append((cd, amt, e))

    streams: list[IncomeStream] = []
    for desc, items in sorted(groups.items()):
        items.sort(key=lambda x: x[0])
        occ = [Occurrence(d, a) for d, a, _ in items]
        if len(occ) < 2:
            continue
        intervals = [(b.dt - a.dt).days for a, b in zip(occ, occ[1:])]
        med = sorted(intervals)[len(intervals) // 2]
        if not (cfg.income_min_interval <= med <= cfg.income_max_interval):
            continue
        if NON_RECURRING_INCOME.search(desc):
            continue
        amts = [a for _, a, _ in items]
        amount = _mode_amount(amts)
        last = items[-1][2]
        streams.append(IncomeStream(
            category=last.category, description=desc, payday=occ[-1].dt, amount=amount))

    # ---- scheduled salary rows: the generator's own next-payday truth
    sched = [e for e in events if e.status == "scheduled" and e.direction == "credit"
             and e.event_type == "income"]
    for e in sorted(sched, key=lambda x: x.cash_date):
        amt_home = (e.amount if e.currency == home
                    else fx.convert(e.amount or ZERO, e.currency, home, e.cash_date))
        # attach to the closest history stream of the same category; else new stream
        cands = [s for s in streams if s.category == e.category]
        best = min(cands, key=lambda s: abs(s.amount - amt_home)) if cands else None
        if best is not None and abs(best.amount - amt_home) <= amt_home * Decimal("0.35"):
            best.payday = e.cash_date
            best.amount = amt_home
            best.source_event = e
        else:
            streams.append(IncomeStream(
                category=e.category, description=e.description, payday=e.cash_date,
                amount=amt_home, source_event=e))

    # ---- "Final employer payroll" style stop signals from descriptions
    last_salary_desc = ""
    for e in events:
        if e.direction == "credit" and e.category == "salary" and e.status == "settled" \
                and e.cash_date < request_date:
            last_salary_desc = e.description
    if re.search(r"final (?:employer )?payroll", last_salary_desc, re.I):
        eff.stop = True

    # ---- apply amendments to salary streams
    for s in streams:
        if s.category != "salary":
            continue
        if eff.stop:
            s.stop_after = request_date
        if eff.resume_date is not None:
            s.start_from = eff.resume_date
            s.payday = eff.resume_date
            if eff.resume_amount is not None:
                s.amount = (eff.resume_amount if eff.resume_currency in (None, home)
                            else fx.convert(eff.resume_amount, eff.resume_currency,
                                            s.currency, eff.resume_date))
        if eff.raise_amount is not None:
            frm = eff.raise_from or request_date
            s.raise_from = frm
            s.raise_amount = (eff.raise_amount if eff.raise_currency in (None, home)
                              else fx.convert(eff.raise_amount, eff.raise_currency,
                                              s.currency, frm))
        if eff.date_move is not None:
            s.payday = eff.date_move
        if eff.next_amount is not None:
            s.next_override = (eff.next_amount if eff.next_currency in (None, home)
                               else fx.convert(eff.next_amount, eff.next_currency,
                                               s.currency, s.payday))
        if eff.first_date is not None:
            s.payday = eff.first_date
            s.start_from = eff.first_date
            if eff.first_amount is not None:
                s.amount = (eff.first_amount if eff.first_currency in (None, home)
                            else fx.convert(eff.first_amount, eff.first_currency,
                                            s.currency, eff.first_date))
    return streams, eff


def project_income(streams: list[IncomeStream], one_time_credits: list, home: str, fx,
                   start: date, end: date, cfg) -> list[tuple[date, Decimal]]:
    """Projected income occurrences (home currency) with cash dates in [start, end]."""
    out: list[tuple[date, Decimal]] = []
    for s in streams:
        if s.category != "salary" and s.source_event is None \
                and not cfg.project_non_salary_income:
            continue
        for k in range(-36, 36):
            d = month_shift(s.payday, k)
            if not (start <= d <= end):
                continue
            if s.start_from is not None and d < s.start_from:
                continue
            if s.stop_after is not None and d > s.stop_after:
                continue
            amt = s.amount
            if s.raise_amount is not None and s.raise_from is not None and d >= s.raise_from:
                amt = s.raise_amount
            if s.next_override is not None and d == s.payday:
                amt = s.next_override
            out.append((d, amt))
    for cd, amt, cur, label in one_time_credits:
        if start <= cd <= end:
            a = amt if cur == home else fx.convert(amt, cur, home, cd)
            out.append((cd, a))
    return out
