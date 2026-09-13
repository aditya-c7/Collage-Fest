"""Field-level calibration scorer against the 25 solved samples.

Run: python evaluation/scorer.py           (requires code/main.py --samples output)

Compares each output field and prints per-field accuracy plus per-request diffs,
so every calibration iteration shows exactly which rules moved.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

FIELDS = ["amount_safe_to_pay", "affordability_status", "recommended_payment_method",
          "payment_plan", "earliest_date_for_full_payment", "spending_changes_needed",
          "decision_explanation"]
NUMERIC = {"amount_safe_to_pay"}


def run_samples(out_path: Path):
    subprocess.run([sys.executable, str(ROOT / "code" / "main.py"), "--samples",
                    "--out", str(out_path)], check=True)


def norm_amount(s: str) -> Decimal:
    return Decimal(s.strip() or "0")


def amounts_close(a: str, b: str) -> bool:
    return abs(norm_amount(a) - norm_amount(b)) <= Decimal("0.005")


def compare(pred_path: Path):
    with open(pred_path, newline="", encoding="utf-8") as f:
        pred = {r["request_id"]: r for r in csv.DictReader(f)}
    with open(ROOT / "dataset" / "sample_requests.csv", newline="", encoding="utf-8") as f:
        gold = {r["request_id"]: r for r in csv.DictReader(f)}

    per_field = {k: [0, 0] for k in FIELDS}
    mismatches = []
    for rid, g in gold.items():
        p = pred.get(rid)
        if p is None:
            mismatches.append((rid, "MISSING ROW", "", ""))
            continue
        for k in FIELDS:
            pv, gv = (p.get(k) or "").strip(), (g.get(k) or "").strip()
            ok = amounts_close(pv, gv) if k in NUMERIC else pv == gv
            per_field[k][1] += 1
            if ok:
                per_field[k][0] += 1
            else:
                mismatches.append((rid, k, gv, pv))

    total_rows = len(gold)
    full_match = sum(1 for rid in gold
                     if all((pred.get(rid, {}).get(k) or "").strip() ==
                            (gold[rid].get(k) or "").strip()
                            for k in FIELDS if k not in NUMERIC)
                     and amounts_close(pred.get(rid, {}).get("amount_safe_to_pay", "x"),
                                       gold[rid]["amount_safe_to_pay"]))
    print(f"\nFULL-ROW MATCH: {full_match}/{total_rows}")
    for k in FIELDS:
        ok, n = per_field[k]
        print(f"  {k:<32} {ok}/{n}  ({100 * ok / max(n, 1):.0f}%)")
    if mismatches:
        print(f"\nMISMATCHES ({len(mismatches)}):")
        for rid, k, gv, pv in mismatches:
            print(f"  {rid} {k}\n    gold: {gv}\n    pred: {pv}")
    return full_match, total_rows


if __name__ == "__main__":
    out = ROOT / "_samples_pred.csv"
    if "--no-run" not in sys.argv:
        run_samples(out)
    fm, n = compare(out)
    sys.exit(0 if fm == n else 1)
