"""Calibration knobs. Every rule that the calibration loop may tune lives here."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    # history window for recurrence detection
    history_days: int = 120
    # expense series classification
    min_occurrences: int = 2
    frequent_min_gap: int = 4
    # variable-amount projection rule for expenses: last|mean|max3|min|min3|mean3
    var_amount_rule: str = "min"
    # separate rule for monthly-varying series (blank = same as var_amount_rule)
    monthly_var_rule: str = ""
    # how frequent (sub-monthly) variable series project:
    #   asis    -> occurrences at median gap with rule amount
    #   drop    -> not projected at all
    #   monthly -> single monthly occurrence of (window total / months)
    frequent_var_mode: str = "asis"
    # monthly anchor: dom = day-of-month of last occurrence; plus30 = last + 30d
    month_anchor_mode: str = "dom"
    # income stream classification
    income_min_interval: int = 25
    income_max_interval: int = 35
    # income amount rule: mode|last|mean|min|min3|max3
    income_var_rule: str = "mode"
    project_non_salary_income: bool = False
    # include same-day (day 0) flows in the day-0 balance
    day0_flows: bool = True
    # forecast window length (days, inclusive of request_date)
    horizon_days: int = 90
    # one-time future flows to include
    include_pending_debits: bool = True
    include_scheduled_debits: bool = True
    include_scheduled_credits: bool = True
    # which date places a one-time flow in the window (FX always uses settlement date)
    flow_date_mode: str = "event_date"  # event_date | settlement
    # rounding mode for FX conversion
    round_half: str = "half_up"
