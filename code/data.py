"""Dataset loading and normalized models for the Buy-or-Wait agent."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from money import D, ZERO, FX, load_fx

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "dataset"


def _date(s: str) -> date | None:
    s = (s or "").strip()
    return date.fromisoformat(s[:10]) if s else None


def _bool(s: str) -> bool:
    return (s or "").strip().lower() == "true"


@dataclass
class Profile:
    user_id: str
    home_currency: str
    balance: Decimal
    min_balance: Decimal
    priorities: list[str]
    protected: list[str]
    willing_reduce: list[str]
    willing_stop: list[str]
    methods: list[str]
    max_installment_months: int | None


@dataclass
class Event:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Decimal | None  # None => blank, must come from image
    currency: str
    event_date: date
    settlement_date: date | None
    status: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: Decimal | None

    @property
    def cash_date(self) -> date:
        return self.settlement_date or self.event_date


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: int | None
    financing_fee: Decimal
    total_payable_amount: Decimal

    def schedule(self) -> list[tuple[date, Decimal]]:
        out = []
        d = self.first_payment_date
        for _ in range(self.number_of_payments):
            out.append((d, self.payment_amount))
            if self.payment_frequency_days:
                d = d + timedelta(days=self.payment_frequency_days)
        return out


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str
    related_event_id: str
    sent_at: datetime
    source_type: str
    text: str


@dataclass
class ImageRef:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str


def _split(s: str) -> list[str]:
    return [x for x in (s or "").split("|") if x.strip()]


def _load(name: str) -> list[dict]:
    with open(DATA / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@dataclass
class Dataset:
    profiles: dict[str, Profile]
    events_by_user: dict[str, list[Event]]
    events_by_id: dict[str, Event]
    requests: list[Request]
    options_by_request: dict[str, list[PaymentOption]]
    messages_by_user: dict[str, list[Message]]
    messages_by_event: dict[str, list[Message]]
    images_by_event: dict[str, ImageRef]
    fx: FX

    @classmethod
    def load(cls, dataset_dir: Path | None = None) -> "Dataset":
        global DATA
        if dataset_dir:
            DATA = dataset_dir

        profiles = {}
        for r in _load("financial_profiles.csv"):
            p = Profile(
                user_id=r["user_id"],
                home_currency=r["home_currency"].strip(),
                balance=D(r["current_available_balance"]),
                min_balance=D(r["minimum_balance_to_keep"]),
                priorities=_split(r["financial_priorities"]),
                protected=_split(r["expense_categories_to_protect"]),
                willing_reduce=_split(r["expense_categories_user_is_willing_to_reduce"]),
                willing_stop=_split(r["expense_categories_user_is_willing_to_stop"]),
                methods=_split(r["payment_methods_user_will_consider"]),
                max_installment_months=int(r["max_installment_months"]) if r["max_installment_months"].strip() else None,
            )
            profiles[p.user_id] = p

        events_by_user: dict[str, list[Event]] = {}
        events_by_id: dict[str, Event] = {}
        for r in _load("financial_events.csv"):
            e = Event(
                event_id=r["event_id"],
                user_id=r["user_id"],
                event_type=r["event_type"],
                description=r["description"],
                category=r["category"],
                direction=r["direction"],
                amount=D(r["amount"]) if r["amount"].strip() else None,
                currency=r["currency"].strip(),
                event_date=_date(r["event_date"]),
                settlement_date=_date(r["settlement_date"]),
                status=r["status"],
                linked_event_id=r["linked_event_id"].strip(),
                flexibility=r["flexibility"],
                minimum_allowed_amount=D(r["minimum_allowed_amount"]) if r["minimum_allowed_amount"].strip() else None,
            )
            events_by_user.setdefault(e.user_id, []).append(e)
            events_by_id[e.event_id] = e

        requests = [
            Request(
                request_id=r["request_id"],
                user_id=r["user_id"],
                request_date=_date(r["request_date"]),
                request_type=r["request_type"],
                requested_amount=D(r["requested_amount"]),
                desired_completion_date=_date(r["desired_completion_date"]),
                allows_partial_payment=_bool(r["allows_partial_payment"]),
                request_text=r["request_text"],
            )
            for r in _load("requests.csv")
        ]

        options_by_request: dict[str, list[PaymentOption]] = {}
        for r in _load("request_payment_options.csv"):
            o = PaymentOption(
                payment_option_id=r["payment_option_id"],
                request_id=r["request_id"],
                payment_method=r["payment_method"],
                payment_amount=D(r["payment_amount"]),
                number_of_payments=int(r["number_of_payments"]),
                first_payment_date=_date(r["first_payment_date"]),
                payment_frequency_days=int(r["payment_frequency_days"]) if r["payment_frequency_days"].strip() else None,
                financing_fee=D(r["financing_fee"]),
                total_payable_amount=D(r["total_payable_amount"]),
            )
            options_by_request.setdefault(o.request_id, []).append(o)

        messages_by_user: dict[str, list[Message]] = {}
        messages_by_event: dict[str, list[Message]] = {}
        for r in _load("messages.csv"):
            m = Message(
                message_id=r["message_id"],
                user_id=r["user_id"],
                request_id=r["request_id"].strip(),
                related_event_id=r["related_event_id"].strip(),
                sent_at=datetime.fromisoformat(r["sent_at"].replace("Z", "+00:00")),
                source_type=r["source_type"],
                text=r["message_text"],
            )
            messages_by_user.setdefault(m.user_id, []).append(m)
            if m.related_event_id:
                messages_by_event.setdefault(m.related_event_id, []).append(m)

        images_by_event: dict[str, ImageRef] = {}
        for r in _load("images.csv"):
            im = ImageRef(r["image_id"], r["user_id"], r["request_id"], r["related_event_id"])
            images_by_event[im.related_event_id] = im

        fx = load_fx(DATA / "exchange_rates.csv")

        return cls(profiles, events_by_user, events_by_id, requests, options_by_request,
                   messages_by_user, messages_by_event, images_by_event, fx)


def sample_requests(ds: Dataset) -> list[Request]:
    """The 25 solved examples as Request objects (calibration set)."""
    with open(DATA / "sample_requests.csv", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        out.append(Request(
            request_id=r["request_id"],
            user_id=r["user_id"],
            request_date=_date(r["request_date"]),
            request_type=r["request_type"],
            requested_amount=D(r["requested_amount"]),
            desired_completion_date=_date(r["desired_completion_date"]),
            allows_partial_payment=_bool(r["allows_partial_payment"]),
            request_text=r["request_text"],
        ))
    return out
