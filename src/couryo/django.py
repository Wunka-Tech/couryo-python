"""Django email backend that sends through the Couryo API.

.. code-block:: python

    # settings.py, Django 6.1+ (MAILERS; EMAIL_BACKEND is deprecated there and cannot be mixed with it)
    MAILERS = {"default": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"api_key": "ck_live_..."}}}
    DEFAULT_FROM_EMAIL = "Shop <hi@example.com>"

    # settings.py, Django 6.0 and older
    EMAIL_BACKEND = "couryo.django.EmailBackend"
    COURYO_API_KEY = "ck_live_..."  # or the COURYO_API_KEY environment variable
    DEFAULT_FROM_EMAIL = "Shop <hi@example.com>"

Every ``EmailMessage`` (or ``EmailMultiAlternatives``) becomes one ``POST /v1/emails``. The
Couryo id of each sent message is stored in ``message.couryo_id``. Special headers:
``X-Couryo-Stream`` (``transactional`` or ``marketing``), ``X-Couryo-Tags`` (``"k=v, k2=v2"``)
and ``Idempotency-Key``; other ``X-*`` headers are passed through.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
from email.message import Message
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

from ._client import Couryo

__all__ = ["EmailBackend", "message_to_request"]

#: Headers that become Couryo options instead of being passed through.
_COURYO_HEADERS = {"x-couryo-stream", "x-couryo-tags", "idempotency-key"}
#: Custom headers passed through to the final message (the rest is rebuilt by the platform).
_PASS_THROUGH = re.compile(r"^(x-[a-z0-9-]+|list-id|precedence|auto-submitted|feedback-id)$", re.IGNORECASE)


def _address(value: Any) -> str:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        name, addr = value
        name = str(name).replace('"', "'")
        return f'"{name}" <{addr}>' if name else str(addr)
    return str(value)


def _addresses(values: Optional[Sequence[Any]]) -> List[str]:
    return [_address(v) for v in (values or []) if v]


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _attachment_from_mime(part: Message, index: int) -> Dict[str, Any]:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        payload = part.as_bytes()
    out: Dict[str, Any] = {
        "filename": part.get_filename() or f"attachment-{index}",
        "content": _b64(payload),
        "content_type": part.get_content_type(),
    }
    cid = part.get("Content-ID")
    if cid:
        out["content_id"] = str(cid).strip().strip("<>")
    return out


def _attachment_content(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    if hasattr(content, "message"):  # a Django EmailMessage attached as message/rfc822
        return content.message().as_bytes()
    if isinstance(content, Message):
        return content.as_bytes()
    return str(content).encode("utf-8")


def _attachments(message: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, att in enumerate(getattr(message, "attachments", None) or [], start=1):
        if isinstance(att, Message):
            out.append(_attachment_from_mime(att, i))
            continue
        filename, content, mimetype = (tuple(att) + (None, None, None))[:3]
        filename = filename or f"attachment-{i}"
        item: Dict[str, Any] = {"filename": filename, "content": _b64(_attachment_content(content))}
        mimetype = mimetype or mimetypes.guess_type(filename)[0]
        if mimetype:
            item["content_type"] = mimetype
        out.append(item)
    return out


def _parse_tags(value: str) -> Dict[str, str]:
    tags: Dict[str, str] = {}
    for pair in value.split(","):
        key, sep, rest = pair.partition("=")
        if key.strip() and sep:
            tags[key.strip()] = rest.strip()
    return tags


def message_to_request(message: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Converts a Django ``EmailMessage`` into ``(SendEmailRequest, idempotency_key)``."""
    extra: Dict[str, Any] = dict(getattr(message, "extra_headers", None) or {})
    lower = {str(k).lower(): (k, v) for k, v in extra.items()}

    from_email = lower["from"][1] if "from" in lower else message.from_email
    to = _addresses(message.to)
    cc = _addresses(message.cc)
    bcc = _addresses(getattr(message, "bcc", None))
    reply_to = _addresses(getattr(message, "reply_to", None))
    if not reply_to and "reply-to" in lower:
        reply_to = [str(lower["reply-to"][1])]
    if not to:
        # Only Cc or Bcc: the first one becomes To (same rule as the SMTP relay).
        if cc:
            to = [cc.pop(0)]
        elif bcc:
            to = [bcc.pop(0)]

    body: Dict[str, Any] = {"from": _address(from_email), "to": to, "subject": str(message.subject or "")}
    if cc:
        body["cc"] = cc
    if bcc:
        body["bcc"] = bcc
    if reply_to:
        body["reply_to"] = reply_to

    content = str(message.body) if message.body else ""
    if content:
        if getattr(message, "content_subtype", "plain") == "html":
            body["html"] = content
        else:
            body["text"] = content
    for alt in getattr(message, "alternatives", None) or []:
        alt_content, mimetype = alt[0], alt[1]
        if mimetype == "text/html" and "html" not in body:
            body["html"] = alt_content.decode("utf-8") if isinstance(alt_content, bytes) else str(alt_content)
        elif mimetype == "text/plain" and "text" not in body:
            body["text"] = alt_content.decode("utf-8") if isinstance(alt_content, bytes) else str(alt_content)

    attachments = _attachments(message)
    if attachments:
        body["attachments"] = attachments

    headers: Dict[str, str] = {}
    idempotency_key: Optional[str] = None
    for key, value in extra.items():
        name = str(key)
        low = name.lower()
        val = str(value)
        if low == "x-couryo-stream":
            stream = val.strip().lower()
            if stream in ("transactional", "marketing"):
                body["stream"] = stream
        elif low == "x-couryo-tags":
            body["tags"] = _parse_tags(val)
        elif low == "idempotency-key":
            idempotency_key = val.strip() or None
        elif low not in _COURYO_HEADERS and _PASS_THROUGH.match(name) and not low.startswith("x-couryo-"):
            headers[name] = val
    if headers:
        body["headers"] = headers
    return body, idempotency_key


class EmailBackend(BaseEmailBackend):
    """Sends Django emails through the Couryo API.

    Settings: ``COURYO_API_KEY`` (falls back to the environment variable) and optionally
    ``COURYO_BASE_URL``. The options ``api_key``, ``base_url``, ``client`` (a ready
    :class:`~couryo.Couryo`) and ``fail_silently`` override them: ``OPTIONS`` of a ``MAILERS``
    entry (Django 6.1+) or keyword arguments of ``get_connection("couryo.django.EmailBackend", ...)``
    (Django 6.0 and older). This class keeps its own ``fail_silently`` attribute and passes only
    ``alias`` and unknown options to ``BaseEmailBackend``, which reports typos in ``OPTIONS``.
    """

    def __init__(
        self,
        fail_silently: bool = False,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        client: Optional[Couryo] = None,
        **kwargs: Any,
    ) -> None:
        # Django 6.1+ passes ``alias`` (MAILERS) and rejects unknown OPTIONS in the base class;
        # older versions accept and ignore extra kwargs. ``fail_silently`` stays here: Django 6.1
        # deprecates it in BaseEmailBackend, and a backend that supports it keeps its own attribute.
        super().__init__(**kwargs)
        self.fail_silently = fail_silently
        self.api_key = api_key or getattr(settings, "COURYO_API_KEY", None) or os.environ.get("COURYO_API_KEY")
        self.base_url = base_url or getattr(settings, "COURYO_BASE_URL", None)
        self.client: Optional[Couryo] = client
        self._owns_client = False

    def open(self) -> bool:
        """Creates the API client. Returns True when a new one was created."""
        if self.client is not None:
            return False
        try:
            self.client = Couryo(self.api_key, base_url=self.base_url)
        except Exception:
            if not self.fail_silently:
                raise
            return False
        self._owns_client = True
        return True

    def close(self) -> None:
        if self.client is not None and self._owns_client:
            try:
                self.client.close()
            finally:
                self.client = None
                self._owns_client = False

    def send_messages(self, email_messages: Sequence[Any]) -> int:
        """Sends each message with ``emails.send`` and returns how many were accepted."""
        if not email_messages:
            return 0
        new_client = self.open()
        if self.client is None:
            return 0
        sent = 0
        try:
            for message in email_messages:
                try:
                    if not message.recipients():
                        continue
                    payload, idempotency_key = message_to_request(message)
                    result = self.client.emails.send(payload, idempotency_key=idempotency_key)  # type: ignore[arg-type]
                    message.couryo_id = (result or {}).get("id")
                    sent += 1
                except Exception:
                    if not self.fail_silently:
                        raise
        finally:
            if new_client:
                self.close()
        return sent
