from __future__ import annotations

import asyncio
import datetime as dt
import re

import httpx
import pytest

from couryo import AsyncCouryo, InvalidRequestError, NetworkError, TierLimitError
from fakes import SEND, FakeApi, api_error

UUID_RE = re.compile(r"^[0-9a-f-]{36}$")


def run(coro):
    return asyncio.run(coro)


def test_async_send_with_auth_and_idempotency_key():
    api = FakeApi([(202, {"id": "msg_1", "status": "queued"})])

    async def main():
        async with api.async_() as c:
            return await c.emails.send(SEND)

    assert run(main()) == {"id": "msg_1", "status": "queued"}
    call = api.calls[0]
    assert call.headers["authorization"] == "Bearer ck_test_abc"
    assert UUID_RE.match(call.headers["idempotency-key"])
    assert call.json == SEND


def test_async_retries_with_the_same_key_and_respects_retry_after():
    api = FakeApi([
        httpx.ConnectError("refused"),
        api_error(500, "internal_error", "api_error"),
        api_error(429, "rate_limited", "rate_limited", {"Retry-After": "3"}),
        (202, {"id": "msg_2", "status": "queued"}),
    ])

    async def main():
        c = api.async_(max_retries=3)
        try:
            return await c.emails.send(SEND, idempotency_key="pedido-42")
        finally:
            await c.aclose()

    assert run(main())["id"] == "msg_2"
    assert len(api.calls) == 4
    assert {c.headers["idempotency-key"] for c in api.calls} == {"pedido-42"}
    assert len(api.sleeps) == 3 and api.sleeps[2] == 3.0


def test_async_sleep_can_be_a_coroutine():
    waited = []

    async def fake_sleep(seconds):
        waited.append(seconds)

    api = FakeApi([api_error(503, "billing_unavailable", "api_error", {"Retry-After": "1"}), (200, {})])

    async def main():
        c = AsyncCouryo("ck_test_abc", http_client=httpx.AsyncClient(transport=api.transport), _sleep=fake_sleep)
        await c.domains.list()

    run(main())
    assert waited == [1.0]


def test_async_errors_are_not_retried_and_network_errors_give_up():
    api = FakeApi([api_error(422, "domain_not_verified")])
    with pytest.raises(InvalidRequestError) as info:
        run(api.async_().emails.send(SEND))
    assert (info.value.status, info.value.code, info.value.param, info.value.request_id) == (422, "domain_not_verified", "to", "req_1")
    assert len(api.calls) == 1

    tier = FakeApi([api_error(429, "monthly_limit_reached", "tier_limit")])
    with pytest.raises(TierLimitError):
        run(tier.async_().emails.send(SEND))
    assert len(tier.calls) == 1

    net = FakeApi([httpx.ConnectTimeout("slow")])
    with pytest.raises(NetworkError):
        run(net.async_(max_retries=1).domains.list())
    assert len(net.calls) == 2


def test_async_204_and_iterate():
    api = FakeApi([
        (204, None),
        (200, {"data": [{"id": "evt_2"}, {"id": "evt_1"}], "has_more": True}),
        (200, {"data": [{"id": "evt_0"}], "has_more": False}),
    ])

    async def main():
        c = api.async_()
        assert await c.webhooks.delete("whk_1") is None
        return [e["id"] async for e in c.events.iterate(email_id="msg_1")]

    assert run(main()) == ["evt_2", "evt_1", "evt_0"]
    assert api.calls[1].path == "/events?limit=100&email_id=msg_1"
    assert api.calls[2].path == "/events?limit=100&email_id=msg_1&starting_after=evt_1"


def test_async_contacts_campaigns_and_events_track():
    api = FakeApi([(200, {})])

    async def main():
        c = api.async_()
        await c.contacts.create({"email": "ana@gmail.com"})
        await c.contacts.get("ana@gmail.com")
        await c.contacts.count({"type": "all"})
        await c.events.track({"contact": {"email": "ana@gmail.com"}, "name": "user.signed_up"})
        await c.campaigns.create({"name": "Outubro"})
        await c.campaigns.schedule("cmp_1", dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc))
        await c.campaigns.test("cmp_1", ["a@loja.com.br", "b@loja.com.br"])
        await c.campaigns.send("cmp_1")
        await c.campaigns.stats("cmp_1")
        await c.emails.batch([SEND])
        await c.aclose()

    run(main())
    assert [f"{x.method} {x.path}" for x in api.calls] == [
        "POST /contacts",
        "GET /contacts/ana%40gmail.com",
        "POST /contacts/count",
        "POST /events",
        "POST /campaigns",
        "POST /campaigns/cmp_1/schedule",
        "POST /campaigns/cmp_1/test",
        "POST /campaigns/cmp_1/send",
        "GET /campaigns/cmp_1/stats",
        "POST /emails/batch",
    ]
    assert api.calls[2].json == {"audience": {"type": "all"}}
    assert api.calls[3].json == {"contact": {"email": "ana@gmail.com"}, "name": "user.signed_up"}
    assert api.calls[5].json == {"scheduled_at": "2026-10-20T12:00:00+00:00"}
    assert api.calls[6].json == {"to": ["a@loja.com.br", "b@loja.com.br"]}
    assert api.calls[9].json == {"emails": [SEND]}


def test_async_context_manager_closes_its_own_client():
    async def main():
        async with AsyncCouryo("ck_test_abc") as c:
            inner = c._http
        return inner

    assert run(main()).is_closed
