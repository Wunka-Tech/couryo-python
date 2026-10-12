"""Errors raised by the Couryo SDK.

Every API error is a :class:`CouryoError` with the same fields as the JSON ``error`` object
(``type``, ``code``, ``message``, ``param``, ``doc_url``, ``request_id``) plus the HTTP ``status``
and ``retry_after`` (seconds, from the ``Retry-After`` header). Subclasses follow ``type``.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Type

__all__ = [
    "CouryoError",
    "InvalidRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "TierLimitError",
    "APIError",
    "NetworkError",
    "error_from_response",
]


class CouryoError(Exception):
    """Base class of every error returned by the Couryo API (or a network failure, status 0)."""

    status: int
    type: str
    code: str
    message: str
    param: Optional[str]
    doc_url: Optional[str]
    request_id: Optional[str]
    retry_after: Optional[float]
    raw: Dict[str, Any]

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        status: int = 0,
        type: Optional[str] = None,
        code: Optional[str] = None,
        param: Optional[str] = None,
        doc_url: Optional[str] = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
        raw: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.status = status
        self.message = message if message is not None else f"HTTP {status}"
        self.type = type or ("network" if status == 0 else "api_error")
        self.code = code or ("network_error" if status == 0 else "unknown")
        self.param = param
        self.doc_url = doc_url
        self.request_id = request_id
        self.retry_after = retry_after
        self.raw = dict(raw or {})
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(status={self.status!r}, type={self.type!r}, code={self.code!r}, "
            f"message={self.message!r}, param={self.param!r}, request_id={self.request_id!r})"
        )


class InvalidRequestError(CouryoError):
    """``invalid_request``: a field is missing or invalid (400 or 422). Fix the request; retrying will not help."""


class AuthenticationError(CouryoError):
    """``authentication``: the API key is missing or invalid (401)."""


class PermissionDeniedError(CouryoError):
    """``permission``: the key lacks the scope, or the action is not allowed for the account (403)."""


class NotFoundError(CouryoError):
    """``not_found``: the resource does not exist (404)."""


class ConflictError(CouryoError):
    """``conflict``: the resource already exists or is in a state that does not allow the action (409)."""


class RateLimitError(CouryoError):
    """``rate_limited``: too many requests per second (429). Retried automatically."""


class TierLimitError(CouryoError):
    """``tier_limit``: a plan limit was reached (daily, monthly, spend, paused sending, AI credits)."""


class APIError(CouryoError):
    """``api_error``: something failed on the Couryo side (5xx). Retried automatically."""


class NetworkError(CouryoError):
    """No HTTP response: connection error or timeout (status 0)."""


_BY_TYPE: Dict[str, Type[CouryoError]] = {
    "invalid_request": InvalidRequestError,
    "authentication": AuthenticationError,
    "permission": PermissionDeniedError,
    "not_found": NotFoundError,
    "conflict": ConflictError,
    "rate_limited": RateLimitError,
    "tier_limit": TierLimitError,
    "api_error": APIError,
    "network": NetworkError,
}

_BY_STATUS: Dict[int, Type[CouryoError]] = {
    0: NetworkError,
    400: InvalidRequestError,
    401: AuthenticationError,
    402: TierLimitError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: InvalidRequestError,
    429: RateLimitError,
}


def _error_class(status: int, type_: Optional[str]) -> Type[CouryoError]:
    if type_ and type_ in _BY_TYPE:
        return _BY_TYPE[type_]
    if status in _BY_STATUS:
        return _BY_STATUS[status]
    if status >= 500:
        return APIError
    return CouryoError


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def error_from_response(
    status: int,
    body: Mapping[str, Any],
    *,
    retry_after: Optional[float] = None,
    request_id: Optional[str] = None,
) -> CouryoError:
    """Builds the right :class:`CouryoError` subclass from the ``error`` object of a response."""
    type_ = _str_or_none(body.get("type"))
    cls = _error_class(status, type_)
    return cls(
        _str_or_none(body.get("message")),
        status=status,
        type=type_,
        code=_str_or_none(body.get("code")),
        param=_str_or_none(body.get("param")),
        doc_url=_str_or_none(body.get("doc_url")),
        request_id=_str_or_none(body.get("request_id")) or request_id,
        retry_after=retry_after,
        raw=body,
    )
