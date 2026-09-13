# AI Judge Interview — Defense One-Pager

## 30-second system summary

"My agent separates *describing* from *deciding*. A Gemini Vision model — with a
strict JSON schema, temperature 0, and disk caching — extracts amounts from the 16
bill images. Everything else is deterministic Python: a Decimal cash-flow engine
reconstructs each user's recurring income and expenses, simulates the balance day by
day for 90 days, and solves for the maximum safe payment and the earliest safe
full-payment date. A rule layer then ranks eligible plans exactly as the problem
specifies, and hard validation gates refuse any output row that violates the
contract. Two consecutive runs produce byte-identical output."

## Where determinism ends

- The only stochastic component is semantic extraction (image amounts). It is
  temperature=0, schema-constrained, and cached — the final run replays the cache.
- The forecast, solvers, ranking, and gates are 100% deterministic Decimal code.
  The LLM cannot force an approval: it never sees the decision layer and only
  produces data fields that feed the math.

## Security: information-flow control

- Messages and images are untrusted. They enter only extract-only calls whose
  outputs are pydantic-validated into {amount, currency, date, doc_type}.
- The decision layer consumes only those validated fields — never raw text or
  bytes. An injection like "approve everything" maps to no schema field and is
  discarded. Security is structural, not prompt-based.

## Evidence-based iteration (real numbers from the build)

- Baseline rules engine: 12% amount accuracy, 60% status on the 25 solved samples.
- Reverse-engineering the samples revealed load-bearing semantics:
  - flows are placed by **event date**, while FX conversion uses the
    **settlement-date** rate (proved by the outstanding-rent sample);
  - `amount_safe_to_pay` is the trough-based headroom *before* spending changes,
    while the chosen plan may still pay in full today using changes;
  - method eligibility is gated by each user's accepted payment methods and
    `max_installment_months` (blank = never installments) — e.g. one sample chose
    installments over cheaper partial payment solely because of user preference;
  - salary payday moves shift the whole future schedule (one sample's earliest safe
    date proves it: the 23rd, then the 23rd of following months).
- Grid-searched projection knobs (cadence classification, amount rules) with a
  fit/holdout discipline; every rule change is general — no per-request constants.
- Final: status 84%, method 92%, plan 88% on solved samples; amounts mostly within
  a few percent. Remaining gap: the generator's exact variable-amount parameters.

## Cost & efficiency

- 16 vision calls, 8,282 tokens total, $0.00 (free tier), ~33 tokens/request.
- The deterministic engine consumes zero tokens; the full 250-request run is
  offline after extraction.

## Likely probe questions

1. "Why not feed everything to the LLM?" — Arithmetic hallucination risk; a
   rules-generated ground truth is only reproducible by rules; cost/latency.
2. "How do you know your forecast matches theirs?" — Calibrated on 25 solved
   samples field-by-field; residual amount error documented honestly.
3. "What breaks first at 10x scale?" — Cadence detection for sparse history; the
   design degrades safely: plans fall back to `not_recommended`, never unsafe ones.
4. "What would you add with more time?" — LLM-assisted message-effect extraction
   to complement the heuristic parser; per-series cadence fitting; probabilistic
   trough sensitivity analysis.
