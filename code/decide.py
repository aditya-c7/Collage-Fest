"""Decision layer: eligibility, deterministic plan ranking, plan builders, explanations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from money import ZERO, fmt_plain, fmt_plan, fmt_group, fmt_date_human


@dataclass
class Plan:
    method: str
    status: str
    payments: list                  # [(date, Decimal)]
    changes: list = field(default_factory=list)   # [("stop", series)] / [("reduce_to", series, amt)]
    option_id: str = ""
    total: Decimal = ZERO
    first_date: date | None = None
    n_payments: int = 0

    def completes_by(self, deadline: date) -> bool:
        return all(d <= deadline for d, _ in self.payments)


def rank_key(p: Plan, deadline: date):
    return (
        0 if p.completes_by(deadline) else 1,   # 1. complete by deadline
        1 if p.changes else 0,                  # 2. no spending changes
        p.total,                                # 3. minimize total paid
        p.first_date,                           # 4. start earlier
        p.n_payments,                           # 5. fewer payments
        p.option_id,                            # 6. lowest payment_option_id
    )


def decide(req, profile, events, msgs, sim):
    """Return the output row for one request."""
    home = profile.home_currency
    methods = profile.methods
    options = sim.ds.options_by_request.get(req.request_id, [])

    safe = sim.amount_safe(req, profile, events, msgs)
    earliest = sim.earliest_full_date(req, profile, events, msgs)

    cands: list[Plan] = []

    # ---- full payment today
    if safe >= req.requested_amount and "full_payment" in methods:
        cands.append(Plan("full_payment", "affordable_now",
                          [(req.request_date, req.requested_amount)]))

    # ---- full payment today with spending changes (changes verified by plan_safe)
    if safe < req.requested_amount and "full_payment" in methods:
        changes, amounts = sim.find_changes(req, profile, events, msgs)
        if changes:
            cands.append(Plan("full_payment", "affordable_with_plan",
                              [(req.request_date, req.requested_amount)], changes))

    # ---- installments (must exactly match a supplied option)
    eligible_opts = []
    for o in options:
        if o.payment_method != "installments":
            continue
        if "installments" not in methods or profile.max_installment_months is None:
            continue
        if o.number_of_payments > profile.max_installment_months:
            continue
        sched = o.schedule()
        if sched[-1][0] > req.desired_completion_date:
            continue
        eligible_opts.append((o, sched))
        if sim.plan_safe(req, profile, events, msgs, sched):
            p = Plan("installments", "affordable_with_plan", sched, [], o.payment_option_id)
            p.total = o.total_payable_amount
            cands.append(p)

    # ---- partial payment: exactly two payments
    if req.allows_partial_payment and "partial_payment" in methods \
            and ZERO < safe < req.requested_amount and earliest is not None \
            and earliest <= req.desired_completion_date:
        sched = [(req.request_date, safe), (earliest, req.requested_amount - safe)]
        if sim.plan_safe(req, profile, events, msgs, sched):
            p = Plan("partial_payment", "affordable_with_plan", sched)
            p.total = req.requested_amount
            cands.append(p)

    # ---- wait until full payment is safe
    if earliest is not None and "full_payment" in methods \
            and earliest <= req.desired_completion_date:
        p = Plan("wait", "affordable_later", [(earliest, req.requested_amount)])
        p.total = req.requested_amount
        cands.append(p)

    # ---- last resort: installments made safe by spending changes
    if not cands:
        for o, sched in eligible_opts:
            changes, _amounts = sim.find_changes(req, profile, events, msgs, schedule=sched)
            if changes:
                p = Plan("installments", "affordable_with_plan", sched, changes,
                         o.payment_option_id)
                p.total = o.total_payable_amount
                cands.append(p)

    if not cands:
        return _row_not_affordable(req, profile, safe, earliest)

    for p in cands:
        if p.total == ZERO:
            p.total = sum(a for _, a in p.payments)
        p.first_date = min(d for d, _ in p.payments)
        p.n_payments = len(p.payments)

    cands.sort(key=lambda p: rank_key(p, req.desired_completion_date))
    best = cands[0]
    return _row(req, profile, best, safe, earliest)


# ------------------------------------------------------------------ rows

def _money(x: Decimal) -> str:
    return fmt_group(x)


def _row(req, profile, best: Plan, safe, earliest):
    plan_str = "|".join(f"{fmt_date_iso(d)}:{fmt_plan(a)}" for d, a in best.payments) \
        if best.payments else "none"
    changes_str = _changes_str(best.changes)
    explanation = _explanation(req, profile, best, safe, earliest)
    return {
        "request_id": req.request_id,
        "amount_safe_to_pay": fmt_plain(safe),
        "affordability_status": best.status,
        "recommended_payment_method": best.method,
        "payment_plan": plan_str,
        "earliest_date_for_full_payment": fmt_date_iso(earliest) if earliest is not None else "",
        "spending_changes_needed": changes_str,
        "decision_explanation": explanation,
    }


def _row_not_affordable(req, profile, safe, earliest):
    variant_b = req.allows_partial_payment and profile.methods == ["partial_payment"]
    cur = profile.home_currency
    if variant_b:
        expl = (f"Do not proceed with the {cur} {_money(req.requested_amount)} request. "
                f"Although {cur} {_money(safe)} is available today, the full amount cannot be "
                f"completed safely within 90 days.")
    else:
        expl = (f"Do not make this payment by {fmt_date_human(req.desired_completion_date)}. "
                f"None of the available options keeps the "
                f"{cur} {_money(profile.min_balance)} minimum protected.")
    return {
        "request_id": req.request_id,
        "amount_safe_to_pay": fmt_plain(safe),
        "affordability_status": "not_affordable",
        "recommended_payment_method": "not_recommended",
        "payment_plan": "none",
        "earliest_date_for_full_payment": "",
        "spending_changes_needed": "none",
        "decision_explanation": expl,
    }


def _changes_str(changes) -> str:
    if not changes:
        return "none"
    parts = []
    for c in changes:
        if c[0] == "stop":
            parts.append(f"stop:{c[1].event_id}")
        else:
            parts.append(f"reduce_to:{c[1].event_id}:{fmt_plan(c[2])}")
    return "|".join(parts)


def fmt_date_iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def _series_desc(s) -> str:
    return (s.description or s.category).strip().lower()


def _explanation(req, profile, best: Plan, safe, earliest) -> str:
    cur = profile.home_currency
    minb = _money(profile.min_balance)

    if best.method == "wait":
        d, amt = best.payments[0]
        if earliest is not None and earliest == req.desired_completion_date:
            return (f"Pay {cur} {_money(amt)} in full on {fmt_date_human(d)}. "
                    f"Paying earlier would take the balance below the {cur} {minb} minimum.")
        return (f"Wait until {fmt_date_human(d)}, then pay {cur} {_money(amt)} in full. "
                f"Paying sooner would put the {cur} {minb} minimum at risk.")
    if best.method == "partial_payment":
        (d1, a1), (d2, a2) = best.payments
        return (f"Pay {cur} {_money(a1)} today and the remaining {cur} {_money(a2)} "
                f"on {fmt_date_human(d2)}. This completes the full request and keeps "
                f"the {cur} {minb} minimum protected.")

    if best.method == "installments":
        n = best.n_payments or len(best.payments)
        d0, a0 = best.payments[0]
        return (f"Use {n} installments of {cur} {_money(a0)}, starting {fmt_date_human(d0)}. "
                f"This leaves at least {cur} {minb} available.")

    # full_payment (today, optionally with changes)
    pay_amt = best.payments[0][1]
    prefix = ""
    stops = [c for c in best.changes if c[0] == "stop"]
    reduces = [c for c in best.changes if c[0] == "reduce_to"]
    bits = []
    for _, s in stops:
        bits.append(f"Stop the {_series_desc(s)}")
    for _, s, new_amt in reduces:
        bits.append(f"Reduce the {_series_desc(s)} to {cur} {_money(new_amt)}")
    if bits:
        prefix = " and ".join(bits) + ", then "
    return (f"{prefix}Pay {cur} {_money(pay_amt)} today. This leaves at least "
            f"{cur} {minb} available over the next 90 days.")
