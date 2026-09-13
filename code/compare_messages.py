"""Cross-check Tier-0 heuristic message parsing vs the Gemini LLM classification.

Prints disagreements so parser gaps can be fixed with real evidence.
Run: python code/compare_messages.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import Dataset

KIND_MAP = {
    # LLM kind -> the Tier-0 attribute it should have set
    "salary_raise": "raise_amount",
    "salary_reduced_next": "next_amount",
    "salary_date_move": "date_move",
    "salary_stop": "stop",
    "salary_resume": "resume_date",
    "salary_first": "first_date",
    "invoice_approved": "one_time_credit",
    "salary_credit_confirmed": "one_time_credit",
    "rent_increase": "rent_increase_pct",
    "failed_debit_retry": "failed_debit_retry",
}


def main():
    ds = Dataset.load()
    llm = json.loads((ROOT / "code" / "extraction_cache" / "message_effects.json").read_text())

    per_user_effects = {}
    for uid, msgs in ds.messages_by_user.items():
        # Tier-0 effects computed against the LATEST request date of that user
        req_dates = [r.request_date for r in ds.requests if r.user_id == uid]
        rd = max(req_dates) if req_dates else None
        if rd is None:
            continue
        eff = parse_effects(msgs, rd)
        per_user_effects[uid] = eff

    disagree = 0
    for uid, msgs in ds.messages_by_user.items():
        eff = per_user_effects.get(uid)
        for m in msgs:
            g = llm.get(m.message_id)
            if g is None:
                continue
            kind = g["kind"]
            if eff is None:
                continue
            attr = KIND_MAP.get(kind)
            tier0_hit = False
            if attr == "raise_amount":
                tier0_hit = eff.raise_amount is not None
            elif attr == "next_amount":
                tier0_hit = eff.next_amount is not None
            elif attr == "date_move":
                tier0_hit = eff.date_move is not None
            elif attr == "stop":
                tier0_hit = eff.stop
            elif attr == "resume_date":
                tier0_hit = eff.resume_date is not None
            elif attr == "first_date":
                tier0_hit = eff.first_date is not None
            elif attr == "one_time_credit":
                tier0_hit = bool(eff.one_time_credits)
            elif attr == "rent_increase_pct":
                tier0_hit = eff.rent_increase_pct is not None
            elif attr == "failed_debit_retry":
                tier0_hit = bool(eff.failed_debit_retry)
            elif kind in ("informational_no_cash", "other"):
                tier0_hit = True  # no effect expected
            if not tier0_hit:
                disagree += 1
                print(f"DISAGREE {m.message_id} [{m.source_type}] llm={kind} "
                      f"amt={g['amount']} {g['currency']} date={g['date']} pct={g['percent']}")
                print(f"   text: {m.text[:140]}")
    print(f"\n{disagree} disagreements")


if __name__ == "__main__":
    main()
