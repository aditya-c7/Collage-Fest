# Rule Changelog (interview evidence)

Every semantic decision and calibration change, newest last. No entry uses
per-request constants; each is a general rule justified by the solved samples.

1. **v1 baseline** — 90-day daily Decimal simulation; amount_safe_to_pay = trough
   headroom before spending changes; earliest = first safe single-payment date;
   eligibility by `payment_methods_user_will_consider` + `max_installment_months`;
   spec ranking rules 1–6.
2. **Flows placed by event_date, FX converted at settlement-date rate.**
   Proof: the outstanding-rent sample (`request_16`) is `affordable_now` in the
   gold data only if the image-resolved rent event (event_date before the request)
   counts as already in the balance. FX timing is stated by AGENTS.md §6.1.
3. **Image-resolved amounts** feed pending/scheduled events (Gemini Vision, cached).
4. **Message families** (Tier-0 multilingual parser, EN/ID): raises with effective
   dates, payday moves (shift the whole schedule — proven by request_07's earliest
   date of the 23rd), seasonal stops, resumes, first-salary dates, next-payroll
   confirmations with one-time arrears (arrears counted once at payday), household
   stream endings (surviving salary kept, ended stream stopped), FX salary credits,
   rent +12%, retried failed debits. Coverage audit: 215/215 messages classified.
5. **Grid calibration** (var rule × frequent-mode × income rule × anchor × day-0):
   best config locked; holdout discipline — no per-request constants anywhere.
6. **Rounding**: ROUND_HALF_UP assumed for the few FX paths (consistent with sample
   installment math); documented as an assumption, not verifiable from the sample.
7. **Investment contributions** verified one-time per user (29/275) — history only,
   already in balance; future ones flow through the one-time path.
8. **Hardening pass (audit response)**: full+changes plans verified via plan_safe;
   spending-change candidates exclude protected categories and are verified by
   simulation before return; reduce floors at `minimum_allowed_amount`; up to three
   changes; installments+changes fallback when no clean plan exists; duplicate
   future debits (same category+amount within 3 days) ignored; validator extended
   to check partial-second-date == earliest, spending-change event validity,
   protected categories, and floors.
