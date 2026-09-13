"""One-shot exploration dump: FX table, blank-amount events, per-sample decisive inputs,
and the message taxonomy. Writes output to _explore_out.txt for fast reading.

Run: python code/explore_deep.py
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"
OUT = ROOT / "_explore_out.txt"


def load(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    rows = {n: load(f"{n}.csv") for n in
            ["requests", "sample_requests", "financial_profiles", "financial_events",
             "request_payment_options", "exchange_rates", "messages", "images"]}
    lines = []
    w = lines.append

    w("=" * 90)
    w("EXCHANGE_RATES (full)")
    for r in rows["exchange_rates"]:
        w(f"  {r['rate_date']} {r['from_currency']}->{r['to_currency']} = {r['rate']}")

    w("=" * 90)
    w("BLANK-AMOUNT EVENTS (all users) + image linkage")
    blank = [e for e in rows["financial_events"] if not e["amount"].strip()]
    img_by_ev = {i["related_event_id"]: i["image_id"] for i in rows["images"]}
    for e in blank:
        w(f"  {e['event_id']} {e['user_id']} {e['event_date']} settle={e['settlement_date']} "
          f"{e['event_type']} {e['category']} {e['direction']} {e['currency']} "
          f"status={e['status']} flex={e['flexibility']} link={e['linked_event_id']} "
          f"img={img_by_ev.get(e['event_id'], '-')}")
        w(f"     desc: {e['description']}")

    w("=" * 90)
    w("MESSAGE TAXONOMY: employer messages mentioning salary numbers/dates (first 12)")
    n = 0
    for m in rows["messages"]:
        if m["source_type"] == "employer" and n < 12:
            n += 1
            w(f"  {m['message_id']} {m['user_id']} req={m['request_id']} ev={m['related_event_id']} sent={m['sent_at'][:10]}")
            w(f"    {m['message_text']}")
    w("--- NON-EMPLOYER MESSAGES (all) ---")
    for m in rows["messages"]:
        if m["source_type"] != "employer":
            w(f"  [{m['source_type']}] {m['message_id']} {m['user_id']} req={m['request_id']} "
              f"ev={m['related_event_id']} sent={m['sent_at'][:10]}")
            w(f"    {m['message_text']}")

    w("=" * 90)
    w("PER-SAMPLE DECISIVE INPUTS (non-settled events, scheduled income, options, expected out)")
    ev_by_user = defaultdict(list)
    for e in rows["financial_events"]:
        ev_by_user[e["user_id"]].append(e)
    for s in rows["sample_requests"]:
        uid, rid, rdate = s["user_id"], s["request_id"], s["request_date"]
        w("-" * 90)
        w(f"{rid} {uid} req_date={rdate} amt={s['requested_amount']} deadline={s['desired_completion_date']} "
          f"partial={s['allows_partial_payment']}")
        p = next(r for r in rows["financial_profiles"] if r["user_id"] == uid)
        w(f"  bal={p['current_available_balance']} min={p['minimum_balance_to_keep']} "
          f"methods={p['payment_methods_user_will_consider']} max_inst={p['max_installment_months']} "
          f"reduce={p['expense_categories_user_is_willing_to_reduce']} "
          f"stop={p['expense_categories_user_is_willing_to_stop']}")
        w(f"  EXPECTED: safe={s['amount_safe_to_pay']} status={s['affordability_status']} "
          f"method={s['recommended_payment_method']}")
        w(f"            plan={s['payment_plan']}")
        w(f"            earliest={s['earliest_date_for_full_payment']} changes={s['spending_changes_needed']}")
        # income events (settled last 2 + all non-settled)
        incs = [e for e in ev_by_user[uid] if e["event_type"] == "income" or e["category"] == "salary"]
        w(f"  INCOME ({len(incs)}):")
        for e in incs:
            w(f"    {e['event_id']} {e['event_date']} settle={e['settlement_date']} amt={e['amount']} "
              f"{e['currency']} status={e['status']} | {e['description']}")
        for e in ev_by_user[uid]:
            if e["status"] != "settled":
                w(f"    NONSETTLED {e['event_id']} {e['event_date']} settle={e['settlement_date']} "
                  f"{e['event_type']} {e['category']} {e['direction']} amt={e['amount']} {e['currency']} "
                  f"status={e['status']} flex={e['flexibility']} min_allowed={e['minimum_allowed_amount']} "
                  f"link={e['linked_event_id']} | {e['description']}")
        for o in rows["request_payment_options"]:
            if o["request_id"] == rid:
                w(f"  OPT {o['payment_option_id']}: {o['payment_method']} amt={o['payment_amount']} "
                  f"n={o['number_of_payments']} first={o['first_payment_date']} freq={o['payment_frequency_days']} "
                  f"fee={o['financing_fee']} total={o['total_payable_amount']}")
        for m in rows["messages"]:
            if m["user_id"] == uid:
                w(f"  MSG {m['message_id']} [{m['source_type']}] req={m['request_id']} ev={m['related_event_id']} sent={m['sent_at'][:10]}")
                w(f"      {m['message_text']}")
        for im in rows["images"]:
            if im["user_id"] == uid:
                w(f"  IMG {im['image_id']} ev={im['related_event_id']}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
