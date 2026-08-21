from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.db.enums import WorkMode
from app.db.models import Job, JobPosting
from app.domains.jobs.normalization import comparison_key

_PEN_CURRENCY_KEYS = {"pen", "s", "sol", "soles"}
_INTERNATIONAL_REMOTE_TERMS = (
    "latam",
    "latin america",
    "latinoamerica",
    "global",
    "worldwide",
    "anywhere",
    "americas",
)
_LOCAL_TERMS = ("peru", "lima")
_NON_MONTHLY_PERIOD_TERMS = ("hour", "hora", "day", "dia", "week", "semana")


def _decimal_from_salary_token(value: str) -> Decimal | None:
    token = value.strip().replace(" ", "")
    if not token:
        return None

    if "," in token and "." in token:
        last_comma = token.rfind(",")
        last_dot = token.rfind(".")
        if last_comma > last_dot:
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        tail = token.rsplit(",", 1)[1]
        token = token.replace(",", "") if len(tail) == 3 else token.replace(",", ".")
    elif "." in token:
        tail = token.rsplit(".", 1)[1]
        if len(tail) == 3:
            token = token.replace(".", "")

    try:
        return Decimal(token)
    except InvalidOperation:
        return None


def monthly_salary_pen(posting: JobPosting | None) -> Decimal | None:
    if posting is None:
        return None

    currency_key = comparison_key(posting.currency)
    structured_amount: Decimal | None = None
    if currency_key in _PEN_CURRENCY_KEYS:
        structured_amount = posting.salary_max or posting.salary_min
        if structured_amount is not None:
            period = comparison_key(posting.salary_period)
            if period and any(term in period for term in ("year", "annual", "anual")):
                return structured_amount / Decimal("12")
            if period and any(term in period for term in _NON_MONTHLY_PERIOD_TERMS):
                return None
            return structured_amount

    text = posting.salary_text
    if not text:
        return None
    key = comparison_key(text) or ""
    has_pen_word = any(
        marker in key.split() for marker in _PEN_CURRENCY_KEYS if marker != "s"
    )
    if not has_pen_word and "s/" not in text.lower():
        return None

    matches = re.findall(
        r"(?:s\s*/|pen|soles?)\s*([0-9][0-9.,]*)",
        text,
        flags=re.IGNORECASE,
    )
    amounts = [amount for token in matches if (amount := _decimal_from_salary_token(token))]
    if not amounts:
        return None

    amount = max(amounts)
    if any(term in key.split() for term in ("anual", "annual", "year", "yearly")):
        amount /= Decimal("12")
    if any(term in key.split() for term in _NON_MONTHLY_PERIOD_TERMS):
        return None
    return amount


def published_salary_unassessed(posting: JobPosting | None) -> bool:
    """Return whether a numeric salary exists but is not normalized to monthly PEN yet."""

    if posting is None or monthly_salary_pen(posting) is not None:
        return False
    if posting.salary_min is not None or posting.salary_max is not None:
        return True
    return bool(posting.salary_text and re.search(r"\d", posting.salary_text))


def is_international_remote(job: Job) -> bool:
    if job.work_mode != WorkMode.REMOTE:
        return False

    # Explicit global/LATAM wording wins over a Peru country value because many platforms set
    # candidate/work-location country to Peru even when the employer is offering a regional role.
    location_key = comparison_key(job.location_text)
    if location_key and any(term in location_key for term in _INTERNATIONAL_REMOTE_TERMS):
        return True
    if location_key and any(term in location_key for term in _LOCAL_TERMS):
        return False

    country_key = comparison_key(job.country)
    if country_key:
        return country_key != "peru"
    return False
