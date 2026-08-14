from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.db.enums import WorkMode

_TRACKING_QUERY_KEYS = {
    "lipi",
    "midsig",
    "midtoken",
    "refid",
    "trk",
    "trkemail",
    "trackingid",
}
_CONFIDENTIAL_COMPANY_KEYS = {
    "confidencial",
    "empresa confidencial",
    "confidential",
    "confidential company",
}


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def comparison_key(value: object | None) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower())
    return re.sub(r"\s+", " ", ascii_text).strip() or None


def is_confidential_company(value: object | None) -> bool:
    key = comparison_key(value)
    return key in _CONFIDENTIAL_COMPANY_KEYS if key else False


def normalize_url(value: object | None) -> str | None:
    raw = clean_text(value)
    if raw is None:
        return None

    try:
        split = urlsplit(raw)
    except ValueError:
        return raw

    if not split.scheme or not split.netloc:
        return raw

    query = []
    for key, item_value in parse_qsl(split.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower.startswith("utm_") or key_lower in _TRACKING_QUERY_KEYS:
            continue
        query.append((key, item_value))

    path = split.path.rstrip("/") or "/"
    return urlunsplit(
        (
            split.scheme.lower(),
            split.netloc.lower(),
            path,
            urlencode(sorted(query)),
            "",
        )
    )


def normalize_work_mode(value: object | None) -> WorkMode:
    key = comparison_key(value)
    if key is None:
        return WorkMode.UNKNOWN
    if any(term in key for term in ("remote", "remoto", "teletrabajo", "work from home")):
        return WorkMode.REMOTE
    if any(term in key for term in ("hybrid", "hibrido", "hibrida")):
        return WorkMode.HYBRID
    if any(term in key for term in ("onsite", "on site", "presencial")):
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def parse_datetime(value: object | None) -> datetime | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = clean_text(value)
        if text is None:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
