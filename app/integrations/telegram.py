from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import get_settings


class TelegramConfigurationError(RuntimeError):
    """Raised when Telegram delivery is enabled without complete credentials."""


class TelegramDeliveryError(RuntimeError):
    """Raised when Telegram rejects or cannot receive a message."""


def send_telegram_message(text: str) -> None:
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value()
    chat_id = settings.telegram_chat_id.strip()
    if not settings.telegram_enabled or not token or not chat_id:
        raise TelegramConfigurationError("Telegram delivery is not fully configured.")

    payload = urlencode({"chat_id": chat_id, "text": text[:4096]}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed HTTPS Telegram host
            body = response.read(64_000)
    except HTTPError as exc:
        raise TelegramDeliveryError(f"Telegram API returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise TelegramDeliveryError("Telegram API request failed.") from exc

    try:
        result = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise TelegramDeliveryError("Telegram API returned an invalid response.") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        description = result.get("description") if isinstance(result, dict) else None
        safe_description = str(description)[:300] if description else "request was rejected"
        raise TelegramDeliveryError(f"Telegram API rejected the message: {safe_description}.")
