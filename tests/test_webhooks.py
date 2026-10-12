from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path

import pytest

from couryo import WebhookVerificationError, sign_webhook, verify_webhook

# Shared with the Node SDK (computed by @couryo/node): both SDKs must accept it.
VECTOR = json.loads(Path(__file__).with_name("webhook-vector.json").read_text(encoding="utf-8"))

HEADERS = {"webhook-id": VECTOR["id"], "webhook-timestamp": str(VECTOR["timestamp"]), "webhook-signature": VECTOR["signature"]}
NOW = VECTOR["timestamp"]


def test_shared_vector_signature_matches_the_node_sdk():
    assert sign_webhook(VECTOR["secret"], VECTOR["id"], VECTOR["timestamp"], VECTOR["body"]) == VECTOR["signature"]


def test_accepts_the_shared_vector():
    event = verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"], now=NOW)
    assert event["type"] == "bounced"
    assert event["data"]["email_id"] == "msg_abc"
    assert event == json.loads(VECTOR["body"])
    # bytes body, datetime now
    when = dt.datetime.fromtimestamp(NOW + 100, tz=dt.timezone.utc)
    assert verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"].encode(), now=when)["data"]["smtp_code"] == "550 5.1.1"


def test_header_styles():
    title = {"Webhook-Id": VECTOR["id"], "WEBHOOK-TIMESTAMP": str(NOW), "Webhook-Signature": VECTOR["signature"]}
    lists = {k: [v, "ignored"] for k, v in HEADERS.items()}
    meta = {"HTTP_WEBHOOK_ID": VECTOR["id"], "HTTP_WEBHOOK_TIMESTAMP": str(NOW), "HTTP_WEBHOOK_SIGNATURE": VECTOR["signature"], "CONTENT_TYPE": "application/json"}
    pairs = list(HEADERS.items())  # e.g. ASGI-like list of pairs
    for headers in (title, lists, meta):
        assert verify_webhook(VECTOR["secret"], headers, VECTOR["body"], now=NOW)["type"] == "bounced"
    assert verify_webhook(VECTOR["secret"], pairs, VECTOR["body"], now=NOW)["type"] == "bounced"


def test_multiple_signatures_any_match_passes():
    headers = {**HEADERS, "webhook-signature": f"v1,AAAA v2,{VECTOR['signature'][3:]} {VECTOR['signature']}"}
    assert verify_webhook(VECTOR["secret"], headers, VECTOR["body"], now=NOW)["type"] == "bounced"
    only_wrong = {**HEADERS, "webhook-signature": f"v1,AAAA v2,{VECTOR['signature'][3:]}"}
    with pytest.raises(WebhookVerificationError, match="signature does not match"):
        verify_webhook(VECTOR["secret"], only_wrong, VECTOR["body"], now=NOW)


def test_wrong_signature_body_or_secret():
    with pytest.raises(WebhookVerificationError, match="signature does not match"):
        verify_webhook(VECTOR["secret"], {**HEADERS, "webhook-signature": "v1,nIcfcxFQhLP2QkIH1kslatq4pADTAwX6hoQmBCWvQXs="}, VECTOR["body"], now=NOW)
    with pytest.raises(WebhookVerificationError, match="signature"):
        verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"].replace("bounced", "delivered"), now=NOW)
    other = "whsec_" + base64.b64encode(b"x" * 24).decode()
    with pytest.raises(WebhookVerificationError, match="signature"):
        verify_webhook(other, HEADERS, VECTOR["body"], now=NOW)


def test_old_or_future_timestamp():
    with pytest.raises(WebhookVerificationError, match="timestamp too old or in the future"):
        verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"], now=NOW + 301)
    with pytest.raises(WebhookVerificationError, match="timestamp too old or in the future"):
        verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"], now=NOW - 301)
    assert verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"], now=NOW + 301, tolerance_seconds=600)["type"] == "bounced"
    with pytest.raises(WebhookVerificationError, match="timestamp"):
        verify_webhook(VECTOR["secret"], HEADERS, VECTOR["body"])  # real clock: the vector is old


def test_missing_headers_and_invalid_timestamp():
    with pytest.raises(WebhookVerificationError, match="missing webhook-id, webhook-timestamp or webhook-signature header"):
        verify_webhook(VECTOR["secret"], {"webhook-id": VECTOR["id"]}, VECTOR["body"], now=NOW)
    with pytest.raises(WebhookVerificationError, match="missing"):
        verify_webhook(VECTOR["secret"], {}, VECTOR["body"], now=NOW)
    with pytest.raises(WebhookVerificationError, match="invalid webhook-timestamp"):
        verify_webhook(VECTOR["secret"], {**HEADERS, "webhook-timestamp": "1791403864.5"}, VECTOR["body"], now=NOW)


def test_body_not_json():
    body = "not json"
    headers = {**HEADERS, "webhook-signature": sign_webhook(VECTOR["secret"], VECTOR["id"], NOW, body)}
    with pytest.raises(WebhookVerificationError, match="body is not JSON"):
        verify_webhook(VECTOR["secret"], headers, body, now=NOW)

