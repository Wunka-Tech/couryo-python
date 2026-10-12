from __future__ import annotations

import datetime as dt
import re

import httpx
import pytest

import couryo
from couryo import (
    APIError,
    ConflictError,
    Couryo,
    CouryoError,
    InvalidRequestError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    TierLimitError,
)
from couryo._base import backoff
from fakes import SEND, FakeApi, api_error

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_send_with_auth_json_and_automatic_idempotency_key():
    api = FakeApi([(202, {"id": "msg_1", "status": "queued"})])
    res = api.sync().emails.send(SEND)
    assert res == {"id": "msg_1", "status": "queued"}
    call = api.calls[0]
    assert call.method == "POST"
    assert call.url == "https://api.couryo.com/v1/emails"
    assert call.headers["authorization"] == "Bearer ck_test_abc"
    assert call.headers["accept"] == "application/json"
    assert call.headers["accept-language"] == "pt-BR"
    assert call.headers["user-agent"] == f"couryo-python/{couryo.__version__}"
    assert call.headers["content-type"] == "application/json"
    assert UUID_RE.match(call.headers["idempotency-key"])
    assert call.json == SEND


def test_get_has_no_body_and_no_idempotency_key():
    api = FakeApi([(200, {"id": "msg_1"})])
    api.sync(language="en", base_url="https://example.test/v1///").emails.get("msg_1")
    call = api.calls[0]
    assert call.url == "https://example.test/v1/emails/msg_1"
    assert "idempotency-key" not in call.headers
    assert "content-type" not in call.headers
    assert call.headers["accept-language"] == "en"
    assert call.content == b""


def test_retries_network_error_5xx_and_rate_limit_with_the_same_key():
    api = FakeApi([httpx.ConnectError("connection refused"), api_error(500, "internal_error", "api_error"), (202, {"id": "msg_2", "status": "queued"})])
    res = api.sync().emails.send(SEND, idempotency_key="pedido-42")
    assert res["id"] == "msg_2"
    assert len(api.calls) == 3
    assert {c.headers["idempotency-key"] for c in api.calls} == {"pedido-42"}
    assert len(api.sleeps) == 2
    assert 0.4 <= api.sleeps[0] <= 0.6 and 0.8 <= api.sleeps[1] <= 1.2

    auto = FakeApi([httpx.ReadTimeout("timed out"), (202, {"id": "msg_3", "status": "queued"})])
    auto.sync().emails.send(SEND)
    assert auto.calls[0].headers["idempotency-key"] == auto.calls[1].headers["idempotency-key"]

    rl = FakeApi([api_error(429, "rate_limited", "rate_limited", {"Retry-After": "0"}), (200, {"data": [], "has_more": False})])
    rl.sync().emails.list()
    assert len(rl.calls) == 2
    assert rl.sleeps == [0.0]


def test_retry_after_is_respected_and_capped():
    api = FakeApi([api_error(429, "rate_limited", "rate_limited", {"Retry-After": "2"}), api_error(409, "idempotency_in_progress", "conflict", {"Retry-After": "120"}), (202, {"id": "msg_1", "status": "queued"})])
    api.sync().emails.send(SEND)
    assert api.sleeps == [2.0, 60.0]
    assert len(api.calls) == 3


def test_does_not_retry_errors_that_would_fail_again():
    api = FakeApi([api_error(422, "domain_not_verified")])
    with pytest.raises(InvalidRequestError) as info:
        api.sync().emails.send(SEND)
    err = info.value
    assert isinstance(err, CouryoError)
    assert (err.status, err.type, err.code, err.param, err.request_id) == (422, "invalid_request", "domain_not_verified", "to", "req_1")
    assert err.message == "msg domain_not_verified" == str(err)
    assert err.doc_url == "https://couryo.com/docs/errors#domain_not_verified"
    assert err.retry_after is None
    assert len(api.calls) == 1 and api.sleeps == []

    tier = FakeApi([api_error(429, "daily_limit_reached", "tier_limit")])
    with pytest.raises(TierLimitError) as tinfo:
        tier.sync().emails.send(SEND)
    assert tinfo.value.code == "daily_limit_reached"
    assert len(tier.calls) == 1

    conflict = FakeApi([api_error(409, "idempotency_conflict", "conflict")])
    with pytest.raises(ConflictError):
        conflict.sync().emails.send(SEND)
    assert len(conflict.calls) == 1

    missing = FakeApi([api_error(404, "resource_not_found", "not_found")])
    with pytest.raises(NotFoundError):
        missing.sync().emails.get("msg_x")


def test_gives_up_after_max_retries():
    api = FakeApi([api_error(503, "billing_unavailable", "api_error", {"Retry-After": "1"})])
    with pytest.raises(APIError) as info:
        api.sync(max_retries=1).domains.list()
    assert info.value.status == 503 and info.value.retry_after == 1.0
    assert len(api.calls) == 2

    net = FakeApi([httpx.ConnectError("down")])
    with pytest.raises(NetworkError) as ninfo:
        net.sync().domains.list()
    assert (ninfo.value.status, ninfo.value.type, ninfo.value.code) == (0, "network", "network_error")
    assert "down" in ninfo.value.message
    assert isinstance(ninfo.value.__cause__, httpx.ConnectError)
    assert len(net.calls) == 3

    none = FakeApi([api_error(500, "internal_error", "api_error")])
    with pytest.raises(APIError):
        none.sync(max_retries=0).domains.list()
    assert len(none.calls) == 1


def test_error_without_json_body():
    api = FakeApi([(502, "Bad gateway")])
    with pytest.raises(APIError) as info:
        api.sync(max_retries=0).domains.list()
    assert info.value.message == "Bad gateway"
    assert (info.value.type, info.value.code) == ("api_error", "unknown")

    empty = FakeApi([(400, b"")])
    with pytest.raises(InvalidRequestError) as einfo:
        empty.sync().domains.list()
    assert einfo.value.message == "HTTP 400"

    by_status = FakeApi([(429, {"error": {"code": "rate_limited", "message": "slow down"}}, {"Request-Id": "req_h"}), (200, {})])
    by_status.sync().domains.list()
    assert len(by_status.calls) == 2


def test_204_returns_none():
    api = FakeApi([(204, None)])
    assert api.sync().domains.delete("dom_1") is None
    assert api.calls[0].method == "DELETE"


def test_query_skips_none_and_empty_values():
    api = FakeApi([(200, {"data": [], "has_more": False})])
    c = api.sync()
    c.emails.list(limit=10, status="bounced", recipient="", tag=None, period="7d")
    c.suppressions.list(q="gmail", reason=None)
    assert api.calls[0].path == "/emails?limit=10&status=bounced&period=7d"
    assert api.calls[1].path == "/suppressions?q=gmail"
    prepared = c._prepare("GET", "/x", query={"a": True, "b": False, "c": 0, "d": None})
    assert prepared.url.endswith("/x?a=true&b=false&c=0")


def test_domains_health_webhooks_suppressions_events_templates_and_batch():
    api = FakeApi([(200, {})])
    c = api.sync()
    c.domains.create("loja.com.br")
    c.domains.health("dom_1", refresh=True)
    c.domains.health("dom_1")
    c.domains.verify("dom_1")
    c.webhooks.update("whk_1", {"enabled": False})
    c.webhooks.create({"url": "https://loja.com.br/hook", "events": ["bounced"]})
    c.suppressions.remove("a+b@gmail.com")
    c.suppressions.add("x@y.com")
    c.events.list(type="bounced", limit=10)
    c.templates.preview("boas-vindas", {"nome": "Ana"})
    c.templates.preview("boas vindas", version=2)
    c.templates.versions("tpl_1")
    c.emails.batch([{"from": "a@b.com", "to": "c@d.com", "subject": "x", "text": "y"}])
    c.emails.check(SEND)
    assert [f"{x.method} {x.path}" for x in api.calls] == [
        "POST /domains",
        "GET /domains/dom_1/health?refresh=1",
        "GET /domains/dom_1/health",
        "POST /domains/dom_1/verify",
        "PATCH /webhooks/whk_1",
        "POST /webhooks",
        "DELETE /suppressions/a%2Bb%40gmail.com",
        "POST /suppressions",
        "GET /events?limit=10&type=bounced",
        "POST /templates/boas-vindas/preview",
        "POST /templates/boas%20vindas/preview",
        "GET /templates/tpl_1/versions",
        "POST /emails/batch",
        "POST /emails/check",
    ]
    bodies = [x.json for x in api.calls]
    assert bodies[0] == {"name": "loja.com.br"}
    assert api.calls[3].content == b"" and "idempotency-key" in api.calls[3].headers
    assert bodies[4] == {"enabled": False}
    assert bodies[7] == {"email": "x@y.com", "stream": "all"}
    assert bodies[9] == {"variables": {"nome": "Ana"}}
    assert bodies[10] == {"variables": {}, "version": 2}
    assert bodies[12] == {"emails": [{"from": "a@b.com", "to": "c@d.com", "subject": "x", "text": "y"}]}


def test_iterate_walks_every_page():
    api = FakeApi([
        (200, {"data": [{"id": "msg_3"}, {"id": "msg_2"}], "has_more": True}),
        (200, {"data": [{"id": "msg_1"}], "has_more": False}),
    ])
    it = api.sync().emails.iterate(status="bounced")
    assert api.calls == []  # lazy generator
    assert [e["id"] for e in it] == ["msg_3", "msg_2", "msg_1"]
    assert api.calls[0].path == "/emails?limit=100&status=bounced"
    assert api.calls[1].path == "/emails?limit=100&status=bounced&starting_after=msg_2"

    empty = FakeApi([(200, {"data": [], "has_more": True})])
    assert list(empty.sync().events.iterate(type="opened")) == []
    assert len(empty.calls) == 1


def test_contacts():
    api = FakeApi([(201, {"id": "con_1"}), (200, {}), (200, {}), (200, {}), (204, None), (200, {"total": 3, "subscribed": 2, "suppressed": 1}), (200, {"data": [{"id": "con_1"}], "has_more": False})])
    c = api.sync()
    assert c.contacts.create({"email": "ana@gmail.com", "attributes": {"plano": "pro"}, "tags": ["cliente"]}, idempotency_key="k1") == {"id": "con_1"}
    c.contacts.list(q="ana", limit=5)
    c.contacts.get("ana+1@gmail.com")
    c.contacts.update("con_1", {"attributes": {"plano": None}})
    assert c.contacts.delete("con_1") is None
    audience = {"type": "segment", "match": "all", "conditions": [{"field": "tag", "op": "eq", "value": "cliente"}]}
    assert c.contacts.count(audience)["total"] == 3
    assert [x["id"] for x in c.contacts.iterate(q="ana")] == ["con_1"]
    assert [f"{x.method} {x.path}" for x in api.calls] == [
        "POST /contacts",
        "GET /contacts?limit=5&q=ana",
        "GET /contacts/ana%2B1%40gmail.com",
        "PATCH /contacts/con_1",
        "DELETE /contacts/con_1",
        "POST /contacts/count",
        "GET /contacts?limit=100&q=ana",
    ]
    assert api.calls[0].json == {"email": "ana@gmail.com", "attributes": {"plano": "pro"}, "tags": ["cliente"]}
    assert api.calls[0].headers["idempotency-key"] == "k1"
    assert api.calls[3].json == {"attributes": {"plano": None}}
    assert api.calls[5].json == {"audience": audience}
    assert c.contacts.upsert == c.contacts.create


def test_events_track():
    api = FakeApi([(201, {"id": "cev_1", "contact_id": "con_1", "name": "order.paid", "enrolled": [], "converted": [], "created_at": "2026-10-08T12:00:00Z"})])
    body = {"contact": {"email": "ana@gmail.com", "attributes": {"cidade": "Recife"}}, "name": "order.paid", "properties": {"total": 99.9}}
    res = api.sync().events.track(body, idempotency_key="pedido-42-pago")
    assert res["id"] == "cev_1"
    assert (api.calls[0].method, api.calls[0].path) == ("POST", "/events")
    assert api.calls[0].json == body
    assert api.calls[0].headers["idempotency-key"] == "pedido-42-pago"


def test_campaigns():
    api = FakeApi([(200, {"id": "cmp_1"})])
    c = api.sync()
    c.campaigns.create({"name": "Outubro", "audience": {"type": "all"}, "from": "Loja <oi@loja.com.br>", "subject": "Novidades", "html": "<p>Oi</p>"})
    c.campaigns.list(status="draft")
    c.campaigns.get("cmp_1")
    c.campaigns.update("cmp_1", {"subject": "Novidades de outubro"})
    c.campaigns.preflight("cmp_1")
    c.campaigns.test("cmp_1", "eu@loja.com.br")
    c.campaigns.test("cmp_1")
    c.campaigns.schedule("cmp_1", dt.datetime(2026, 10, 20, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=-3))))
    c.campaigns.schedule("cmp_1", dt.datetime(2026, 10, 20, 12, 30, 15, 999))
    c.campaigns.schedule("cmp_1", "2026-10-20T12:30:00Z")
    c.campaigns.send("cmp_1", idempotency_key="disparo-outubro")
    c.campaigns.pause("cmp_1")
    c.campaigns.resume("cmp_1")
    c.campaigns.cancel("cmp_1")
    c.campaigns.stats("cmp_1")
    c.campaigns.delete("cmp_1")
    assert [f"{x.method} {x.path}" for x in api.calls] == [
        "POST /campaigns",
        "GET /campaigns?status=draft",
        "GET /campaigns/cmp_1",
        "PATCH /campaigns/cmp_1",
        "POST /campaigns/cmp_1/preflight",
        "POST /campaigns/cmp_1/test",
        "POST /campaigns/cmp_1/test",
        "POST /campaigns/cmp_1/schedule",
        "POST /campaigns/cmp_1/schedule",
        "POST /campaigns/cmp_1/schedule",
        "POST /campaigns/cmp_1/send",
        "POST /campaigns/cmp_1/pause",
        "POST /campaigns/cmp_1/resume",
        "POST /campaigns/cmp_1/cancel",
        "GET /campaigns/cmp_1/stats",
        "DELETE /campaigns/cmp_1",
    ]
    calls = api.calls
    assert calls[0].json["from"] == "Loja <oi@loja.com.br>"
    assert calls[3].json == {"subject": "Novidades de outubro"}
    assert calls[4].content == b"" and "content-type" not in calls[4].headers
    assert calls[5].json == {"to": ["eu@loja.com.br"]}
    assert calls[6].json == {}
    assert calls[7].json == {"scheduled_at": "2026-10-20T09:30:00-03:00"}
    assert calls[8].json == {"scheduled_at": "2026-10-20T12:30:15+00:00"}
    assert calls[9].json == {"scheduled_at": "2026-10-20T12:30:00Z"}
    assert calls[10].headers["idempotency-key"] == "disparo-outubro"
    for call in calls:
        assert ("idempotency-key" in call.headers) == (call.method == "POST")


def test_datetime_values_in_bodies_are_serialized():
    api = FakeApi([(202, {"id": "msg_1", "status": "queued"})])
    api.sync().emails.send({**SEND, "scheduled_at": dt.datetime(2026, 10, 9, 8, 0, tzinfo=dt.timezone.utc)})
    assert api.calls[0].json["scheduled_at"] == "2026-10-09T08:00:00+00:00"


def test_requires_an_api_key(monkeypatch):
    monkeypatch.delenv("COURYO_API_KEY", raising=False)
    with pytest.raises(ValueError, match="missing API key"):
        Couryo()
    monkeypatch.setenv("COURYO_API_KEY", "ck_test_env")
    api = FakeApi([(200, {})])
    Couryo(http_client=httpx.Client(transport=api.transport)).domains.list()
    assert api.calls[0].headers["authorization"] == "Bearer ck_test_env"


def test_backoff():
    assert backoff(1, 2) == 2.0
    assert backoff(1, 300) == 60.0
    for _ in range(50):
        assert 1.6 <= backoff(3) <= 2.4
        assert 6.4 <= backoff(10) <= 9.6


def test_context_manager_closes_only_its_own_client():
    with Couryo("ck_test_abc") as c:
        inner = c._http
    assert inner.is_closed

    own = httpx.Client(transport=FakeApi([(200, {})]).transport)
    with Couryo("ck_test_abc", http_client=own):
        pass
    assert not own.is_closed
    own.close()
