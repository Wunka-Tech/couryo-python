# couryo (Python)

Official Python SDK for the [Couryo](https://couryo.com) email API. [Leia em português](https://github.com/Wunka-Tech/couryo-python/blob/main/README.pt-BR.md).

- Sync (`Couryo`) and async (`AsyncCouryo`) clients on top of `httpx`, the only dependency.
- Type hints from the API contract: `TypedDict`s in `couryo.types` for requests and responses (plain dicts at runtime).
- Automatic `Idempotency-Key` on every POST, reused on retries: a send that timed out but went through is never duplicated.
- Retries with backoff for network errors, `5xx` and `rate_limited` (honors `Retry-After`). Errors that would fail again (`domain_not_verified`, `daily_limit_reached`...) are raised right away.
- Webhook verification (Standard Webhooks) in one call.
- Django email backend (`couryo.django.EmailBackend`).
- Python 3.9 or newer.

> Not on PyPI yet. Inside the Couryo monorepo it lives in `packages/sdk-python` (`pip install -e packages/sdk-python`).

## Install

```bash
pip install couryo
# with the Django backend
pip install "couryo[django]"
```

## Send an email

```python
import os
from couryo import Couryo

couryo = Couryo(api_key=os.environ["COURYO_API_KEY"])  # ck_live_... or ck_test_... (COURYO_API_KEY is also read by default)

res = couryo.emails.send({
    "from": "Shop <orders@example.com>",
    "to": "ana@example.com",
    "subject": "Order 1042 confirmed",
    "html": "<p>Thanks!</p>",
    "text": "Thanks!",
    "tags": {"kind": "order"},
})
print(res["id"], res["status"])
```

`Couryo` can be used as a context manager (`with Couryo() as couryo: ...`) or closed with `couryo.close()`.

### Async

```python
import asyncio
from couryo import AsyncCouryo

async def main():
    async with AsyncCouryo() as couryo:
        res = await couryo.emails.send({"from": "Shop <orders@example.com>", "to": "ana@example.com", "subject": "Hi", "text": "Hello!"})
        async for email in couryo.emails.iterate(status="bounced"):
            print(email["id"])

asyncio.run(main())
```

Outside `async with`, call `await couryo.aclose()` when you are done.

## Idempotency

Every POST gets an `Idempotency-Key` (a random UUID), reused on every retry. Pass your own key when the same business event may be sent twice:

```python
couryo.emails.send(body, idempotency_key="order-1042-confirmation")
```

## Saved templates

```python
couryo.templates.create({"name": "welcome", "subject": "Welcome, {{name}}!", "html": "<h1>Hi, {{name}}</h1>"})
couryo.emails.send({"from": "Shop <hi@example.com>", "to": "ana@example.com", "template": "welcome", "variables": {"name": "Ana"}})
```

## Contacts, events and campaigns

```python
# Create or update a contact (same email = merge attributes)
couryo.contacts.create({"email": "ana@example.com", "attributes": {"plan": "pro"}, "tags": ["customer"]})

# A contact event can start sequences
couryo.events.track(
    {"contact": {"email": "ana@example.com"}, "name": "order.paid", "properties": {"total": 99.9}},
    idempotency_key="order-1042-paid",
)

# A campaign to a segment
audience = {"type": "segment", "conditions": [{"field": "tag", "op": "eq", "value": "customer"}]}
print(couryo.contacts.count(audience))
campaign = couryo.campaigns.create({
    "name": "October news",
    "audience": audience,
    "from": "Shop <news@example.com>",
    "subject": "What is new in October",
    "html": "<p>Hi!</p>",
})
check = couryo.campaigns.preflight(campaign["id"])
if check["can_send"]:
    couryo.campaigns.schedule(campaign["id"], "2026-10-20T09:00:00-03:00")  # or a datetime
```

## Errors

```python
from couryo import CouryoError, InvalidRequestError, RateLimitError

try:
    couryo.emails.send(body)
except InvalidRequestError as e:
    print(e.code, e.param)  # e.g. domain_not_verified, from
except CouryoError as e:
    print(e.status, e.type, e.code, e.message, e.param, e.doc_url, e.request_id, e.retry_after)
```

Subclasses follow the error `type`: `InvalidRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `ConflictError`, `RateLimitError`, `TierLimitError`, `APIError` and `NetworkError` (no response, `status` 0). `message` follows the `language` option (`pt-BR` by default, or `en`). A missing API key raises `ValueError` when the client is created.

## Webhooks

Use the raw body exactly as it arrived. `verify_webhook` returns the event (`{type, timestamp, data}`) or raises `WebhookVerificationError` for a wrong signature or a timestamp older than 5 minutes.

Flask:

```python
import os
from flask import Flask, request
from couryo import verify_webhook, WebhookVerificationError

app = Flask(__name__)

@app.post("/webhooks/couryo")
def couryo_webhook():
    try:
        event = verify_webhook(os.environ["COURYO_WEBHOOK_SECRET"], request.headers, request.get_data())
    except WebhookVerificationError:
        return "", 400
    if event["type"] == "bounced":
        ...  # event["data"]["email_id"], event["data"]["recipient"], event["data"]["explanation"]
    return "", 200
```

FastAPI:

```python
import os
from fastapi import FastAPI, HTTPException, Request
from couryo import verify_webhook, WebhookVerificationError

app = FastAPI()

@app.post("/webhooks/couryo")
async def couryo_webhook(request: Request):
    try:
        event = verify_webhook(os.environ["COURYO_WEBHOOK_SECRET"], request.headers, await request.body())
    except WebhookVerificationError:
        raise HTTPException(status_code=400)
    return {"ok": True}
```

Django (`request.headers` or `request.META` both work):

```python
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from couryo import verify_webhook, WebhookVerificationError

@csrf_exempt
@require_POST
def couryo_webhook(request):
    try:
        event = verify_webhook(settings.COURYO_WEBHOOK_SECRET, request.headers, request.body)
    except WebhookVerificationError:
        return HttpResponseBadRequest()
    return HttpResponse(status=200)
```

## Django email backend

On Django 6.1 or newer, configure it in `MAILERS` (the options `api_key`, `base_url`, `client` and `fail_silently` go in `OPTIONS`):

```python
# settings.py
import os

MAILERS = {
    "default": {
        "BACKEND": "couryo.django.EmailBackend",
        "OPTIONS": {"api_key": os.environ["COURYO_API_KEY"]},  # without it: the COURYO_API_KEY setting or environment variable
    },
}
DEFAULT_FROM_EMAIL = "Shop <hi@example.com>"
```

With more than one entry in `MAILERS`, pick one with `send_mail(..., using="alias")` or `msg.send(using="alias")`.

On Django 6.0 or older, use `EMAIL_BACKEND` (Django 6.1 still accepts it with a deprecation warning, but not together with `MAILERS`):

```python
# settings.py
import os

EMAIL_BACKEND = "couryo.django.EmailBackend"
COURYO_API_KEY = os.environ["COURYO_API_KEY"]  # falls back to the COURYO_API_KEY environment variable
# COURYO_BASE_URL = "https://api.couryo.com/v1"  # optional
DEFAULT_FROM_EMAIL = "Shop <hi@example.com>"
```

`send_mail`, `EmailMessage` and `EmailMultiAlternatives` then go through the API: one `emails.send` per message, with `from_email`, `to`, `cc`, `bcc`, `reply_to`, `subject`, the body (text, or HTML when `content_subtype = "html"`), the `text/html` alternative and attachments (Base64; images with `Content-ID` become inline). Headers:

- `X-Couryo-Stream: marketing` (or `transactional`, the default);
- `X-Couryo-Tags: kind=order, store=downtown`;
- `Idempotency-Key: order-1042` (otherwise one is generated);
- other `X-*` headers are passed through.

The id of each sent message is stored in `message.couryo_id`. `fail_silently` is honored (on Django 6.1, as an `OPTIONS` entry) and `send_messages` returns how many messages were accepted.

```python
from django.core.mail import EmailMultiAlternatives

msg = EmailMultiAlternatives("Order 1042 confirmed", "Thanks!", to=["ana@example.com"], headers={"X-Couryo-Tags": "kind=order"})
msg.attach_alternative("<p>Thanks!</p>", "text/html")
msg.send()
print(msg.couryo_id)
```

### Or SMTP, without the SDK

Django's SMTP backend also works with Couryo (same headers `X-Couryo-Stream` and `X-Couryo-Tags`). On Django 6.1 or newer:

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.couryo.com",
            "port": 587,  # STARTTLS (2525 also uses STARTTLS; 465 is TLS with "use_ssl": True instead of "use_tls")
            "username": "couryo",
            "password": os.environ["COURYO_API_KEY"],  # key with the send or admin scope
            "use_tls": True,
        },
    },
}
```

On Django 6.0 or older:

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.couryo.com"
EMAIL_PORT = 587  # STARTTLS (2525 also uses STARTTLS; 465 is TLS with EMAIL_USE_SSL = True)
EMAIL_HOST_USER = "couryo"
EMAIL_HOST_PASSWORD = os.environ["COURYO_API_KEY"]  # key with the send or admin scope
EMAIL_USE_TLS = True
```

## Everything else

| Resource | Methods |
|---|---|
| `emails` | `send`, `batch` (up to 100), `check`, `get`, `list`, `iterate` |
| `domains` | `list`, `create`, `get`, `delete`, `verify`, `health` (deliverability diagnosis, `refresh=True`) |
| `webhooks` | `list`, `create`, `get`, `update`, `delete` |
| `suppressions` | `list`, `add(email, stream="all")`, `remove` |
| `events` | `list`, `iterate` (delivery events), `track` (contact event) |
| `templates` | `list`, `create`, `get`, `update`, `delete`, `versions`, `preview(id_or_name, variables)` |
| `contacts` | `create` (upsert), `list`, `get` (id or email), `update`, `delete`, `iterate`, `count(audience)` |
| `campaigns` | `create`, `list`, `get`, `update`, `delete`, `preflight`, `send`, `schedule`, `pause`, `resume`, `cancel`, `test(id, to=None)`, `stats` |

Every POST method accepts `idempotency_key=`. `iterate` walks every page: `for email in couryo.emails.iterate(status="bounced"): ...` (`async for` in `AsyncCouryo`).

Options: `api_key`, `base_url`, `max_retries` (2), `timeout` (30 s per attempt), `language`, `http_client` (your own `httpx.Client` or `httpx.AsyncClient`, which the SDK does not close).

Docs: https://couryo.com/en/docs
