"""Deep-dive exploration workbook: for each sample request, dump every input that
determines its outcome, next to the expected output. This is the calibration oracle.

Run: python code/explore_samples.py [request_id ...]
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"


def load(name):
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt(r, keys):
    return {k: r.get(k, "") for k in keys}


def main():
    rows = {n: load(f"{n}.csv") for n in
            ["requests", "sample_requests", "financial_profiles", "financial_events",
             "request_payment_options", "exchange_rates", "messages", "images", "output"]}

    want = set(sys.argv[1:])
    samples = [r for r in rows["sample_requests"] if not want or r["request_id"] in want]

    for s in samples:
        rid, uid, rdate = s["request_id"], s["user_id"], s["request_date"]
        print("\n" + "#" * 100)
        print(f"REQUEST {rid} | user {uid} | date {rdate} | type {s['request_type']} | "
              f"amount {s['requested_amount']} | deadline {s['desired_completion_date']} | "
              f"partial {s['allows_partial_payment']}")
        print(f"  text: {s['request_text']}")

        p = rows["financial_profiles"][0]
        for r in rows["financial_profiles"]:
            if r["user_id"] == uid:
                p = r
        print(f"PROFILE: bal={p['current_available_balance']} min={p['minimum_balance_to_keep']} "
              f"cur={p['home_currency']}")
        print(f"  priorities={p['financial_priorities']}")
        print(f"  protect={p['expense_categories_to_protect']}")
        print(f"  reduce={p['expense_categories_user_is_willing_to_reduce']}")
        print(f"  stop={p['expense_categories_user_is_willing_to_stop']}")
        print(f"  methods={p['payment_methods_user_will_consider']} max_inst_months={p['max_installment_months']}")

        print("OPTIONS:")
        for o in rows["request_payment_options"]:
            if o["request_id"] == rid:
                print(f"  {o['payment_option_id']}: {o['payment_method']} amt={o['payment_amount']} "
                      f"n={o['number_of_payments']} first={o['first_payment_date']} "
                      f"freq={o['payment_frequency_days']} fee={o['financing_fee']} total={o['total_payable_amount']}")

        print("MESSAGES (user):")
        for m in rows["messages"]:
            if m["user_id"] == uid:
                print(f"  {m['message_id']} req={m['request_id']} ev={m['related_event_id']} "
                      f"sent={m['sent_at']} src={m['source_type']}")
                print(f"    {m['message_text']}")

        print("IMAGES (user):")
        for im in rows["images"]:
            if im["user_id"] == uid:
                print(f"  {im['image_id']} req={im['request_id']} ev={im['related_event_id']}")

        # events: history (settled) for the 120 days before request date, plus all
        # pending/scheduled/cancelled/failed/unrealized + blank amounts, any date
        from datetime import date
        rd = date.fromisoformat(rdate)
        hist, other = [], []
        for e in rows["financial_events"]:
            if e["user_id"] != uid:
                continue
            ed = e["event_date"][:10]
            if e["status"] in ("settled",) and ed < rdate:
                d = (rd - date.fromisoformat(ed)).days
                if d <= 120:
                    hist.append((ed, e))
            elif e["status"] != "settled" or not e["amount"]:
                other.append((ed, e))
        hist.sort(key=lambda x: x[0])
        print(f"HISTORY last 120d before {rdate} ({len(hist)} rows):")
        for ed, e in hist:
            print(f"  {ed} {e['event_type']:<20} {e['category']:<20} {e['direction']:<8} "
                  f"{e['amount']:>14} {e['currency']} {e['status']:<9} flex={e['flexibility']:<22} "
                  f"min_allowed={e['minimum_allowed_amount']:<8} link={e['linked_event_id']} "
                  f"settle={e['settlement_date']} | {e['description']}")
        print(f"NON-SETTLED / BLANK-AMOUNT events ({len(other)} rows):")
        for ed, e in sorted(other, key=lambda x: x[0]):
            print(f"  {ed} {e['event_id']} {e['event_type']:<20} {e['category']:<20} "
                  f"{e['direction']:<8} {e['amount']:>14} {e['currency']} {e['status']:<9} "
                  f"flex={e['flexibility']:<22} min_allowed={e['minimum_allowed_amount']:<8} "
                  f"link={e['linked_event_id']} settle={e['settlement_date']} | {e['description']}")

        print("EXPECTED OUTPUT:")
        for k in ["amount_safe_to_pay", "affordability_status", "recommended_payment_method",
                  "payment_plan", "earliest_date_for_full_payment", "spending_changes_needed",
                  "decision_explanation"]:
            print(f"  {k}: {s[k]}")


if __name__ == "__main__":
    main()
