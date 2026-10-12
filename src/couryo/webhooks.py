"""Webhook verification (Standard Webhooks).

Couryo signs every webhook call with the headers ``webhook-id``, ``webhook-timestamp`` and
``webhook-signature: v1,<base64(HMAC-SHA256(base64decode(secret without whsec_), "id.timestamp.body"))>``.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import re
import time
from typing import TYPE_CHECKING, Any, Mapping, Optional, Union

if TYPE_CHECKING:
    from .types import WebhookPayload

__all__ = ["WebhookVerificationError", "verify_webhook", "sign_webhook"]

_INT_RE = re.compile(r"^\s*-?\d+\s*$")


class WebhookVerificationError(Exception):
    """The webhook call is not authentic (wrong signature, old timestamp, missing headers) or not JSON."""


def _to_bytes(body: Union[str, bytes, bytearray, memoryview]) -> bytes:
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)


def _secret_key(secret: str) -> bytes:
    raw = secret[len("whsec_"):] if secret.startswith("whsec_") else secret
    raw = raw.strip()
    return base64.b64decode(raw + "=" * (-len(raw) % 4))


def _first(value: Any) -> Optional[str]:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, bytes):
        value = value.decode("latin-1")
    if value is None:
        return None
    return str(value)


def _header(headers: Any, name: str) -> Optional[str]:
    """Case-insensitive lookup in any mapping (dict, Django ``request.headers`` or ``request.META``,
    Flask/Werkzeug and Starlette headers). Lists take the first value."""
    getter = getattr(headers, "get", None)
    if callable(getter):
        try:
            value = _first(getter(name))
        except Exception:  # pragma: no cover - exotic header objects
            value = None
        if value:
            return value
    meta_key = "HTTP_" + name.upper().replace("-", "_")
    items = headers.items() if hasattr(headers, "items") else headers
    for key, value in items:
        if not isinstance(key, str):
            continue
        if key.lower() == name or key == meta_key:
            found = _first(value)
            if found:
                return found
    return None


def sign_webhook(secret: str, id: str, timestamp: int, body: Union[str, bytes]) -> str:
    """Standard Webhooks signature: ``v1,`` + base64(HMAC-SHA256(key, "id.timestamp.body")). Useful in tests."""
    message = f"{id}.{int(timestamp)}.".encode("utf-8") + _to_bytes(body)
    digest = hmac.new(_secret_key(secret), message, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


def verify_webhook(
    secret: str,
    headers: Union[Mapping[str, Any], Any],
    body: Union[str, bytes],
    *,
    tolerance_seconds: int = 300,
    now: Optional[Union[_dt.datetime, int, float]] = None,
) -> "WebhookPayload":
    """Checks a Couryo webhook call and returns the parsed event ``{type, timestamp, data}``.

    Pass the raw body exactly as received (not re-serialized JSON). Raises
    :class:`WebhookVerificationError` when a header is missing, the signature does not match or
    the timestamp is more than ``tolerance_seconds`` (5 minutes) away from now.
    """
    raw = _to_bytes(body)
    msg_id = _header(headers, "webhook-id")
    ts = _header(headers, "webhook-timestamp")
    sigs = _header(headers, "webhook-signature")
    if not msg_id or not ts or not sigs:
        raise WebhookVerificationError("missing webhook-id, webhook-timestamp or webhook-signature header")
    if not _INT_RE.match(ts):
        raise WebhookVerificationError("invalid webhook-timestamp")
    seconds = int(ts)
    if now is None:
        current = int(time.time())
    elif isinstance(now, _dt.datetime):
        current = int(now.timestamp())
    else:
        current = int(now)
    if abs(current - seconds) > tolerance_seconds:
        raise WebhookVerificationError("timestamp too old or in the future")
    expected = sign_webhook(secret, msg_id, seconds, raw)[3:].encode("ascii")
    ok = False
    for entry in sigs.split():
        parts = entry.split(",")
        if len(parts) < 2 or parts[0] != "v1" or not parts[1]:
            continue
        if hmac.compare_digest(parts[1].encode("utf-8"), expected):
            ok = True
    if not ok:
        raise WebhookVerificationError("signature does not match")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise WebhookVerificationError("body is not JSON") from None
