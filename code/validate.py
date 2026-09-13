"""Deterministic safety gates: every output row must satisfy the problem contract
before it is written. These gates cannot be overridden by any upstream component."""
from __future__ import annotations

from decimal import Decimal

from money import D

VALID_STATUS = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
VALID_METHOD = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
STOP_FLEX = {"stoppable", "reducible_or_stoppable"}
REDUCE_FLEX = {"reducible", "reducible_or_stoppable"}


def validate_row(row, req, profile, events=None) -> list[str]:
    """Return a list of contract violations (empty = row is valid)."""
    problems = []

    safe = D(row["amount_safe_to_pay"])
    if not (Decimal(0) <= safe <= req.requested_amount):
        problems.append(f"amount_safe_to_pay {safe} outside [0, {req.requested_amount}]")

    if row["affordability_status"] not in VALID_STATUS:
        problems.append(f"bad status {row['affordability_status']}")
    if row["recommended_payment_method"] not in VALID_METHOD:
        problems.append(f"bad method {row['recommended_payment_method']}")

    status = row["affordability_status"]
    method = row["recommended_payment_method"]
    if status == "affordable_now" and method != "full_payment":
        problems.append("affordable_now must use full_payment")
    if status == "affordable_later" and method != "wait":
        problems.append("affordable_later must use wait")
    if status == "not_affordable" and method != "not_recommended":
        problems.append("not_affordable must use not_recommended")
    if method in ("full_payment", "partial_payment", "installments") \
            and status not in ("affordable_now", "affordable_with_plan"):
        problems.append(f"{method} incompatible with status {status}")

    # earliest-date couplings
    ed = row["earliest_date_for_full_payment"]
    if status == "affordable_now":
        if ed != req.request_date.isoformat():
            problems.append(f"affordable_now earliest must be request_date, got {ed!r}")
    if status == "not_affordable" and ed != "":
        problems.append("not_affordable earliest must be empty")

    # plan couplings
    plan = row["payment_plan"]
    if method == "not_recommended" and plan != "none":
        problems.append("not_recommended plan must be none")
    if method == "wait":
        if plan == "none":
            problems.append("wait plan must have one payment")
        else:
            d, a = plan.split(":")
            if ed and d != ed:
                problems.append("wait payment date must equal earliest_date_for_full_payment")
            if D(a) != req.requested_amount:
                problems.append("wait payment must be the full requested amount")
    if method == "partial_payment":
        parts = plan.split("|") if plan != "none" else []
        if len(parts) != 2:
            problems.append("partial payment needs exactly two payments")
        else:
            (d1, a1), (d2, a2) = [p.split(":") for p in parts]
            if d1 != req.request_date.isoformat():
                problems.append("partial first payment must be on request_date")
            if D(a1) != safe:
                problems.append("partial first payment must equal amount_safe_to_pay")
            if D(a1) + D(a2) != req.requested_amount:
                problems.append("partial payments must sum to requested_amount")
            if ed and d2 != ed:
                problems.append("partial second payment must be on earliest_date_for_full_payment")
            if d2 > req.desired_completion_date.isoformat():
                problems.append("partial second payment after deadline")

    # spending changes: syntax + deep validity against the event data
    sc = row["spending_changes_needed"]
    if sc != "none":
        seen = set()
        actions = []
        for part in sc.split("|"):
            if part.startswith("stop:"):
                eid = part.split(":", 1)[1]
                actions.append(("stop", eid, None))
            elif part.startswith("reduce_to:"):
                _, eid, amt = part.split(":", 2)
                if D(amt) < 0:
                    problems.append(f"negative reduce amount {amt}")
                actions.append(("reduce_to", eid, D(amt)))
            else:
                problems.append(f"bad spending change {part!r}")
                continue
            if eid in seen:
                problems.append("stop and reduce on the same event")
            seen.add(eid)
        if len(seen) > 3:
            problems.append("more than three spending changes")

        if events is not None:
            by_id = {e.event_id: e for e in events}
            protected = set(profile.protected)
            for action, eid, amt in actions:
                e = by_id.get(eid)
                if e is None:
                    problems.append(f"spending change on unknown event {eid}")
                    continue
                if action == "stop":
                    if e.flexibility not in STOP_FLEX:
                        problems.append(f"stop on non-stoppable event {eid} ({e.flexibility})")
                    if e.category not in profile.willing_stop:
                        problems.append(f"stop on category user will not stop: {e.category}")
                else:
                    if e.flexibility not in REDUCE_FLEX:
                        problems.append(f"reduce on non-reducible event {eid} ({e.flexibility})")
                    if e.category not in profile.willing_reduce:
                        problems.append(f"reduce on category user will not reduce: {e.category}")
                    if e.minimum_allowed_amount is not None and amt is not None \
                            and amt < e.minimum_allowed_amount:
                        problems.append(f"reduce_to below minimum_allowed_amount for {eid}")
                if e.category in protected:
                    problems.append(f"spending change on protected category: {e.category}")

    # explanation presence
    if not row["decision_explanation"].strip():
        problems.append("empty decision_explanation")

    return problems
