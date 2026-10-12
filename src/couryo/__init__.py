"""Official Python SDK for the Couryo email API.

.. code-block:: python

    from couryo import Couryo

    couryo = Couryo()  # reads COURYO_API_KEY
    couryo.emails.send({"from": "Shop <hi@example.com>", "to": "ana@example.com", "subject": "Hi", "text": "Hello!"})
"""

from ._async_client import AsyncCouryo
from ._base import DEFAULT_BASE_URL, SDK_VERSION
from ._client import Couryo
from ._version import __version__
from .errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    CouryoError,
    InvalidRequestError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TierLimitError,
)
from .webhooks import WebhookVerificationError, sign_webhook, verify_webhook

__all__ = [
    "__version__",
    "Couryo",
    "AsyncCouryo",
    "DEFAULT_BASE_URL",
    "SDK_VERSION",
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
    "WebhookVerificationError",
    "verify_webhook",
    "sign_webhook",
]
