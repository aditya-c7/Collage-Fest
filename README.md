# HackerRank Orchestrate

Starter repository for the **HackerRank Orchestrate** 24-hour hackathon (September 2026).

## Buy or Wait?

Build an AI-powered financial agent that decides whether a user can safely afford a requested expense.

A user may ask: **"Can I afford this laptop?"**

Answering well takes more than the current balance. The agent must account for recurring expenses, pending payments, essential spending, confirmed income, available payment options, and relevant details buried in messages and images.

For every request, the agent decides whether the user should pay in full, pay partially, use installments, wait, or not proceed. The recommendation must be personalized: two users with the same balance can deserve different answers based on their commitments, priorities, payment preferences, and willingness to adjust flexible expenses.

A recommendation is safe only if the user can complete the full payment plan, cover essential expenses, and stay above their preferred minimum balance throughout the forecast period.

Read [`problem_statement.md`](./problem_statement.md) for the full task spec, input/output schema, allowed values, conflict-resolution rules, and submission format.

---

## Quick Start

Clone the repository and move into the project directory:

```bash
git clone https://github.com/interviewstreet/hackerrank-orchestrate-september26.git
cd hackerrank-orchestrate-september26
```

Build your solution in `code/main.py`, or use another language and document its entry point clearly.

Your solution must:

- Read the input files from `dataset/`
- Generate one prediction for every request
- Write the final predictions to `output.csv` in the repository root

Run the starter Python entry point with:

```bash
python3 code/main.py
```

After running your solution, confirm that `output.csv` exists in the repository root and contains the required columns and one row for every request.

## Important File Locations

```text
dataset/        Input data and the blank output template. Do not modify the input data.
code/           Your solution code.
output.csv      Final generated predictions in the repository root.
code.zip        ZIP file containing your complete solution for submission.
```

The blank template at `dataset/output.csv` is provided as a reference. Your final generated file must be the root-level `output.csv`.

---

## Repository Layout

```text
.
├── AGENTS.md                         # Rules for AI coding tools + transcript logging
├── problem_statement.md              # Full challenge statement
├── README.md                         # You are here
├── code/                             # Your solution code
├── output.csv                        # Final generated predictions
└── dataset/
    ├── requests.csv                  # 250 requests to evaluate — predict these
    ├── output.csv                    # Blank submission template
    ├── sample_requests.csv           # 25 solved examples
    ├── financial_profiles.csv        # Balances, minimum balance, priorities, preferences
    ├── financial_events.csv          # Historical, pending, and confirmed transactions
    ├── request_payment_options.csv   # Payment options available per request
    ├── exchange_rates.csv            # Fixed, dated conversion rates
    ├── messages.csv                  # Messages tied to users, requests, or events
    ├── images.csv                    # Payroll letters, statements, bills, receipts
    └── media/
        └── images/
```

Only `dataset/requests.csv` requires predictions. Everything else is context. Join user records with `user_id`, request records with `request_id`, supporting evidence with `related_event_id`, and exchange rates with the rate date and currency pair.

Amounts are in the user's `home_currency` — the dataset uses INR, ZAR, IDR, USD, and EUR, and every conversion rate you need is in `exchange_rates.csv`. All dates are `YYYY-MM-DD`. Live exchange rates, market data, and banking access are not required.

---

## What You Need to Build

For every row in `dataset/requests.csv`, produce one row in `output.csv` with:

| Column | Meaning |
|---|---|
| `request_id` | The request being answered |
| `amount_safe_to_pay` | Largest amount safe to pay on `request_date` before optional spending changes, after protecting essentials and the minimum balance |
| `affordability_status` | `affordable_now`, `affordable_with_plan`, `affordable_later`, or `not_affordable` |
| `recommended_payment_method` | `full_payment`, `partial_payment`, `installments`, `wait`, or `not_recommended` |
| `payment_plan` | Chronological `<YYYY-MM-DD>:<amount>` entries joined by `\|`, or `none` |
| `earliest_date_for_full_payment` | Earliest date the full amount is forecast safe as one payment; empty if never within the forecast |
| `spending_changes_needed` | Up to three `stop:<event_id>` / `reduce_to:<event_id>:<amount>` changes joined by `\|`, or `none` |
| `decision_explanation` | Short explanation and the financial facts behind it |

`0 <= amount_safe_to_pay <= requested_amount` must always hold. Installment plans must exactly match a supplied payment option, and only recurring expenses marked flexible may be changed.

`affordable_with_plan` means the full request is completed through a partial-payment schedule, installments, or permitted spending changes. Recommend `partial_payment` only when the request allows it, the user accepts it, `0 < amount_safe_to_pay < requested_amount`, and `earliest_date_for_full_payment` is on or before `desired_completion_date`. Use exactly two payments: pay `amount_safe_to_pay` on `request_date`, then pay the remaining amount on `earliest_date_for_full_payment`. The two payments must add up to `requested_amount`. Unlike installments, partial payment does not need to match a supplied payment option.

---

## Suggested Workflow

1. Inspect `dataset/sample_requests.csv` — 25 requests with completed output columns — to understand the expected format and decision style.
2. Reconstruct each user's financial state from `financial_profiles.csv` and `financial_events.csv`: separate recurring expenses from one-time events, reserve pending transactions, count confirmed salary only on its settlement date, and de-duplicate repeated representations of the same event.
3. When an event has a blank `amount`, find its `event_id` as `related_event_id` in `images.csv` and extract the amount from the linked image. Never treat a blank amount as zero. Pull in any other relevant messages, images, and payment options for the request.
4. Forecast forward and generate a plan that keeps the balance above the minimum at every step.
5. Verify deterministically — bounds, plan feasibility, schedule match, flexible-only spending changes — before writing `output.csv`.
6. Score yourself on the solved samples, then run the full dataset.

You may use any language or runtime. Python, JavaScript, and TypeScript are all reasonable choices.

---

## Requirements

Your solution must:

- be runnable from the terminal
- read the provided files from `dataset/`
- produce a valid `output.csv` with the exact required columns in the exact required order
- include one prediction for every `request_id` in `dataset/requests.csv`
- not use organizer-only files or hardcoded labels
- keep behavior deterministic where possible

If you use API keys or secrets, read them from environment variables. Never hardcode secrets in the repo.

---

## Evaluation

Your `output.csv` will be compared against hidden ground-truth values.

The scoring will consider:

- accuracy of `amount_safe_to_pay`
- correctness of `affordability_status`
- correctness of `recommended_payment_method` and `payment_plan`
- accuracy of `earliest_date_for_full_payment`
- validity of `spending_changes_needed`
- usefulness and consistency of `decision_explanation`

### Token Usage And Cost Analysis

Your `code.zip` must include one token-usage file:

```text
evaluation/usage_report.md
```

The report must cover model providers and names, model calls, input and output tokens, total and average tokens per request, estimated total and per-request cost. The reported values must correspond to the final full-dataset run that produced your `output.csv`.

---

## Chat Transcript Logging

This repo includes an [`AGENTS.md`](./AGENTS.md) file for AI coding tools. It asks compatible tools to append conversation summaries to a `log.txt` in the repository root — the same directory as `AGENTS.md`:

| Platform | Path |
|---|---|
| macOS / Linux | `<repo root>/log.txt` |
| Windows | `<repo root>\log.txt` |

The path resolves relative to `AGENTS.md`, so it stays correct across clones, renames, and checkouts. `log.txt` is gitignored — upload it as your chat transcript at submission time. Do not paste secrets into the chat.

In case, the harness you are using is not in the repo root, you can explicitly ask the agent to look for the AGENTS.md in this folder & then continue.

---

## Submission

Submit the following files as instructed by HackerRank:

| File | Description |
|---|---|
| `code.zip` | Full runnable solution, prompts/configuration, README, and the required `evaluation/` folder |
| `output.csv` | Predictions for every row in `dataset/requests.csv` |
| `chat_transcript` | The `log.txt` described above, showing how you developed or used the system |

Before submitting, confirm:

- `output.csv` has one row per row in `dataset/requests.csv` (250 rows plus the header).
- `output.csv` has the exact required columns in the exact required order.
- Every `amount_safe_to_pay` satisfies `0 <= amount_safe_to_pay <= requested_amount`.
- Every installment plan matches a supplied payment option, and every spending change targets a flexible recurring expense.
- Your runnable code, setup instructions, and `evaluation/` folder are included in `code.zip`.

---

# Solution Documentation

## Run

```bash
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt   # Windows (Git Bash)
python code/main.py                                      # writes ./output.csv (250 rows)
```

Optional:
- `python code/main.py --samples` — run the 25 solved sample requests
- `python evaluation/scorer.py` — field-by-field accuracy vs the solved samples
- `python code/extract_images.py` — re-extract amounts from bill images (needs `GEMINI_API_KEY`)

The pipeline is **deterministic and offline-capable**: model extractions are cached
in `code/extraction_cache/`, so `output.csv` reproduces exactly with no API key and
no network access. Two consecutive runs are byte-identical.

## Architecture

```
dataset/ ─> data.py        loaders, joins, Decimal money, dated FX (direct → inverse → USD bridge)
        ─> extract_images.py  Gemini Vision, JSON-schema-constrained, disk-cached,
        │                     injection-hardened (extract-only; images are untrusted data)
        ─> recurring.py    recurring-expense series from settled history (cadence + amount rules)
        ─> income.py       salary streams + message amendments (raises, date moves, stops,
        │                  resumes, approved invoices) via multilingual Tier-0 heuristics
        ─> forecast.py     90-day daily Decimal balance simulation;
        │                  amount_safe_to_pay / earliest_date_for_full_payment solvers
        ─> decide.py       eligibility (user preferences, max_installment_months) →
        │                  deterministic plan ranking (spec rules 1–6) → explanations
        ─> validate.py     hard safety gates before any row is written
        ─> main.py         orchestration → output.csv
```

### Design principles

1. **The model describes; deterministic code decides.** Model calls are confined to
   extracting structured facts from untrusted messages/images. Every amount, date,
   and decision comes from Decimal arithmetic over the supplied CSVs.
2. **Information-flow control by construction.** Untrusted text or image bytes never
   reach the decision layer — only validated, schema-constrained fields do. Embedded
   instructions in messages or images cannot influence any recommendation.
3. **Calibrated rules, not hardcoded answers.** Decision semantics were reverse-
   engineered from `dataset/sample_requests.csv` (the 25 solved examples) with
   `evaluation/scorer.py` reporting per-field accuracy. No request-specific values
   or labels are embedded anywhere.
4. **Physical safety gates.** `validate.py` recomputes plan arithmetic and refuses
   any row violating the contract: amount bounds, status↔method couplings,
   `affordable_now ⇒ earliest == request_date`, partial-payment two-payment
   summation, installment schedules matching a supplied option.

## Key semantics implemented (validated on the solved samples)

- `amount_safe_to_pay`: max payable today *before* optional spending changes such
  that the 90-day daily balance never dips below `minimum_balance_to_keep`
- `earliest_date_for_full_payment`: first day a single full payment passes the same
  safety check without spending changes (capacity only, independent of preferences)
- installment plans must exactly match a supplied payment option and respect
  `max_installment_months`; partial payment is exactly two payments summing to the
  requested amount; `wait` pays in full on the earliest safe date and requires the
  user to accept `full_payment`
- flows are placed by **event date**; FX conversion uses the **settlement-date** rate
  (direct pair → inverse → USD bridge, full Decimal precision)
- messages amend state: salary raises (with effective dates), payday moves (which
  shift the whole schedule), seasonal stops, resume dates, first-salary dates,
  approved invoices (confirmed future income), rent increases (+12%), retried failed
  debits; pending credits, cancelled, failed, and unrealized records are ignored

## Calibration results (25 solved samples)

| Field | Accuracy |
|---|---|
| affordability_status | 21/25 |
| recommended_payment_method | 23/25 |
| payment_plan | 22/25 |
| earliest_date_for_full_payment | 20/25 |
| spending_changes_needed | 22/25 |
| amount_safe_to_pay (exact to the cent) | 4/25 — majority within ~1–5% |

Token usage and cost for the final run: see [`evaluation/usage_report.md`](./evaluation/usage_report.md)
(total $0.00 — all extraction calls ran on the Gemini free tier and are cached).
