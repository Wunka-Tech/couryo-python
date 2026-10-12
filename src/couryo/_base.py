"""Transport logic shared by the sync and async clients.

Request building, the retry decision, the backoff and the response parsing live here, as a
small sans-I/O state machine (:meth:`BaseClient._flow`). Each client only drives it: it performs
the HTTP call or the sleep the flow asks for and sends the outcome back.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import random
import uuid
from typing import Any, Callable, Dict, Generator, Mapping, Optional, Tuple, Union
from urllib.parse import quote, urlencode

import httpx

from ._version import __version__
from .errors import CouryoError, NetworkError, error_from_response

DEFAULT_BASE_URL = "https://api.couryo.com/v1"
SDK_VERSION = __version__

__all__ = ["DEFAULT_BASE_URL", "SDK_VERSION", "BaseClient", "PreparedRequest", "backoff", "enc", "to_iso"]


def enc(value: str) -> str:
    """URL-encodes a path parameter (``a+b@x.com`` becomes ``a%2Bb%40x.com``)."""
    return quote(str(value), safe="")


def to_iso(value: Union[str, _dt.datetime, _dt.date]) -> str:
    """ISO 8601 with offset. Naive datetimes are treated as UTC."""
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_dt.timezone.utc)
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date)):
        return to_iso(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.datetime, _dt.date)):
        return to_iso(value)
    return str(value)


def backoff(attempt: int, retry_after: Optional[float] = None) -> float:
    """Seconds to wait before retry ``attempt`` (1-based).

    ``Retry-After`` when given (at most 60 s), otherwise 0.5 s, 1 s, 2 s... with jitter, at most 8 s.
    """
    if retry_after is not None and math.isfinite(retry_after):
        return min(max(retry_after, 0.0), 60.0)
    base = min(8.0, 0.5 * 2 ** (attempt - 1))
    return base * (0.8 + random.random() * 0.4)


def _retry_after(headers: Mapping[str, str]) -> Optional[float]:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def is_retryable(err: CouryoError) -> bool:
    """Retry what can change with time; never a 4xx that would fail again (never ``idempotency_conflict``)."""
    return (
        err.status >= 500
        or (err.status == 429 and err.code == "rate_limited")
        or err.code == "idempotency_in_progress"
    )


class PreparedRequest:
    __slots__ = ("method", "url", "headers", "content")

    def __init__(self, method: str, url: str, headers: Dict[str, str], content: Optional[bytes]) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.content = content


# Actions yielded by the flow: ("send", PreparedRequest) or ("sleep", seconds).
Action = Tuple[str, Any]
Flow = Generator[Action, Any, Any]


class BaseClient:
    """Configuration and transport logic common to :class:`~couryo.Couryo` and :class:`~couryo.AsyncCouryo`."""

    base_url: str
    max_retries: int
    timeout: float
    language: str

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        max_retries: int = 2,
        timeout: float = 30.0,
        language: str = "pt-BR",
        _sleep: Optional[Callable[[float], Any]] = None,
    ) -> None:
        key = api_key or os.environ.get("COURYO_API_KEY")
        if not key:
            raise ValueError("Couryo: missing API key. Pass api_key=... or set COURYO_API_KEY.")
        self._api_key = key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.language = language
        if _sleep is not None:
            self._sleep = _sleep

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(base_url={self.base_url!r})"

    # Request building -------------------------------------------------------------------

    def _prepare(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PreparedRequest:
        url = self.base_url + path
        params = [(k, _query_value(v)) for k, v in (query or {}).items() if v is not None and v != ""]
        if params:
            url += "?" + urlencode(params)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Accept-Language": self.language,
            "User-Agent": f"couryo-python/{SDK_VERSION}",
        }
        content: Optional[bytes] = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8")
        # Same key on every retry: a POST that timed out but went through is never sent twice.
        if method == "POST":
            headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        return PreparedRequest(method, url, headers, content)

    # Response parsing -------------------------------------------------------------------

    @staticmethod
    def _parse(response: httpx.Response) -> Tuple[bool, Any]:
        """``(True, data)`` for 2xx (``None`` for 204 or an empty body), ``(False, CouryoError)`` otherwise."""
        if response.status_code == 204:
            return True, None
        text = response.text
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        if 200 <= response.status_code < 300:
            return True, data
        error = data.get("error") if isinstance(data, dict) else None
        if not isinstance(error, dict):
            error = {"message": text[:300] or f"HTTP {response.status_code}"}
        return False, error_from_response(
            response.status_code,
            error,
            retry_after=_retry_after(response.headers),
            request_id=response.headers.get("request-id"),
        )

    # The flow ---------------------------------------------------------------------------

    def _flow(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Flow:
        """Yields ``("send", request)`` (expects an ``httpx.Response`` or the transport exception back)
        and ``("sleep", seconds)``; returns the decoded JSON or raises :class:`CouryoError`."""
        request = self._prepare(method, path, body=body, query=query, idempotency_key=idempotency_key)
        attempt = 0
        while True:
            outcome = yield ("send", request)
            if isinstance(outcome, BaseException):
                if attempt >= self.max_retries:
                    raise NetworkError(f"Network error: {outcome}") from outcome
                attempt += 1
                yield ("sleep", backoff(attempt))
                continue
            ok, result = self._parse(outcome)
            if ok:
                return result
            if not is_retryable(result) or attempt >= self.max_retries:
                raise result
            attempt += 1
            yield ("sleep", backoff(attempt, result.retry_after))
