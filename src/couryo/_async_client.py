"""Asynchronous client: :class:`AsyncCouryo`."""

from __future__ import annotations

import asyncio
import datetime as _dt
import inspect
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Dict, List, Mapping, Optional, Sequence, Union

import httpx

from ._base import BaseClient, Flow, enc, to_iso

if TYPE_CHECKING:
    from types import TracebackType

    from .types import (
        Audience,
        AudienceCount,
        BatchSendResponse,
        Campaign,
        CampaignList,
        CampaignPreflight,
        CampaignStats,
        CampaignStatus,
        CheckEmailResponse,
        Contact,
        ContactList,
        CreateCampaignRequest,
        CreateTemplateRequest,
        CreateWebhookRequest,
        Domain,
        DomainHealth,
        DomainList,
        Email,
        EmailEvent,
        EmailEventList,
        EmailEventType,
        EmailList,
        EmailStatus,
        Period,
        PreviewTemplateResponse,
        SendEmailRequest,
        SendEmailResponse,
        Suppression,
        SuppressionList,
        SuppressionReason,
        SuppressionStream,
        Template,
        TemplateList,
        TemplateVersionList,
        TestCampaignResponse,
        TrackEventRequest,
        TrackEventResponse,
        UpdateCampaignRequest,
        UpdateContactRequest,
        UpdateTemplateRequest,
        UpdateWebhookRequest,
        UpsertContactRequest,
        Webhook,
        WebhookList,
    )

__all__ = ["AsyncCouryo"]

DateLike = Union[str, _dt.datetime]


def _to_list(value: Union[str, Sequence[str]]) -> List[str]:
    return [value] if isinstance(value, str) else list(value)


class _Resource:
    def __init__(self, client: "AsyncCouryo") -> None:
        self._c = client

    async def _paginate(self, path: str, query: Dict[str, Any]) -> AsyncIterator[Any]:
        """Walks every page (cursor pagination, newest first)."""
        after: Optional[str] = None
        while True:
            page = await self._c._request("GET", path, query={**query, "starting_after": after})
            data = (page or {}).get("data") or []
            for item in data:
                yield item
            if not page or not page.get("has_more") or not data:
                return
            after = data[-1]["id"]


class Emails(_Resource):
    async def send(self, body: "SendEmailRequest", *, idempotency_key: Optional[str] = None) -> "SendEmailResponse":
        """Queues one email (202). A POST retried by the SDK reuses the same Idempotency-Key."""
        return await self._c._request("POST", "/emails", body=body, idempotency_key=idempotency_key)

    async def batch(self, emails: Sequence["SendEmailRequest"], *, idempotency_key: Optional[str] = None) -> "BatchSendResponse":
        """Up to 100 emails; one result per item, in order."""
        return await self._c._request("POST", "/emails/batch", body={"emails": list(emails)}, idempotency_key=idempotency_key)

    async def check(self, body: "SendEmailRequest", *, idempotency_key: Optional[str] = None) -> "CheckEmailResponse":
        """Checks content and sender before sending (nothing is sent)."""
        return await self._c._request("POST", "/emails/check", body=body, idempotency_key=idempotency_key)

    async def get(self, id: str) -> "Email":
        return await self._c._request("GET", f"/emails/{enc(id)}")

    async def list(
        self,
        *,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
        status: Optional["EmailStatus"] = None,
        recipient: Optional[str] = None,
        tag: Optional[str] = None,
        period: Optional["Period"] = None,
    ) -> "EmailList":
        query = {"limit": limit, "starting_after": starting_after, "status": status, "recipient": recipient, "tag": tag, "period": period}
        return await self._c._request("GET", "/emails", query=query)

    def iterate(
        self,
        *,
        status: Optional["EmailStatus"] = None,
        recipient: Optional[str] = None,
        tag: Optional[str] = None,
        period: Optional["Period"] = None,
        limit: int = 100,
    ) -> AsyncIterator["Email"]:
        """``async for email in couryo.emails.iterate(status="bounced"): ...``"""
        return self._paginate("/emails", {"limit": limit, "status": status, "recipient": recipient, "tag": tag, "period": period})


class Domains(_Resource):
    async def list(self) -> "DomainList":
        return await self._c._request("GET", "/domains")

    async def create(self, name: str, *, idempotency_key: Optional[str] = None) -> "Domain":
        return await self._c._request("POST", "/domains", body={"name": name}, idempotency_key=idempotency_key)

    async def get(self, id: str) -> "Domain":
        return await self._c._request("GET", f"/domains/{enc(id)}")

    async def delete(self, id: str) -> None:
        return await self._c._request("DELETE", f"/domains/{enc(id)}")

    async def verify(self, id: str, *, idempotency_key: Optional[str] = None) -> "Domain":
        return await self._c._request("POST", f"/domains/{enc(id)}/verify", idempotency_key=idempotency_key)

    async def health(self, id: str, *, refresh: bool = False) -> "DomainHealth":
        """Deliverability diagnosis (read only). ``refresh=True`` runs every check now."""
        return await self._c._request("GET", f"/domains/{enc(id)}/health", query={"refresh": 1} if refresh else None)


class Webhooks(_Resource):
    async def list(self) -> "WebhookList":
        return await self._c._request("GET", "/webhooks")

    async def create(self, body: "CreateWebhookRequest", *, idempotency_key: Optional[str] = None) -> "Webhook":
        """The secret (whsec_...) comes back only here: store it."""
        return await self._c._request("POST", "/webhooks", body=body, idempotency_key=idempotency_key)

    async def get(self, id: str) -> "Webhook":
        return await self._c._request("GET", f"/webhooks/{enc(id)}")

    async def update(self, id: str, body: "UpdateWebhookRequest") -> "Webhook":
        return await self._c._request("PATCH", f"/webhooks/{enc(id)}", body=body)

    async def delete(self, id: str) -> None:
        return await self._c._request("DELETE", f"/webhooks/{enc(id)}")


class Suppressions(_Resource):
    async def list(
        self,
        *,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
        q: Optional[str] = None,
        reason: Optional["SuppressionReason"] = None,
    ) -> "SuppressionList":
        return await self._c._request("GET", "/suppressions", query={"limit": limit, "starting_after": starting_after, "q": q, "reason": reason})

    async def add(self, email: str, *, stream: "SuppressionStream" = "all", idempotency_key: Optional[str] = None) -> "Suppression":
        return await self._c._request("POST", "/suppressions", body={"email": email, "stream": stream}, idempotency_key=idempotency_key)

    async def remove(self, email: str) -> None:
        return await self._c._request("DELETE", f"/suppressions/{enc(email)}")


class Events(_Resource):
    async def list(
        self,
        *,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
        type: Optional["EmailEventType"] = None,
        email_id: Optional[str] = None,
    ) -> "EmailEventList":
        """Email delivery events (for whoever missed a webhook)."""
        return await self._c._request("GET", "/events", query={"limit": limit, "starting_after": starting_after, "type": type, "email_id": email_id})

    def iterate(self, *, type: Optional["EmailEventType"] = None, email_id: Optional[str] = None, limit: int = 100) -> AsyncIterator["EmailEvent"]:
        return self._paginate("/events", {"limit": limit, "type": type, "email_id": email_id})

    async def track(self, body: "TrackEventRequest", *, idempotency_key: Optional[str] = None) -> "TrackEventResponse":
        """Records a contact event (``user.signed_up``, ``order.paid``...): it can start sequences (201)."""
        return await self._c._request("POST", "/events", body=body, idempotency_key=idempotency_key)


class Templates(_Resource):
    async def list(self) -> "TemplateList":
        return await self._c._request("GET", "/templates")

    async def create(self, body: "CreateTemplateRequest", *, idempotency_key: Optional[str] = None) -> "Template":
        return await self._c._request("POST", "/templates", body=body, idempotency_key=idempotency_key)

    async def get(self, id_or_name: str) -> "Template":
        """By id (tpl_...) or by name."""
        return await self._c._request("GET", f"/templates/{enc(id_or_name)}")

    async def update(self, id_or_name: str, body: "UpdateTemplateRequest") -> "Template":
        """Content changes create a new version."""
        return await self._c._request("PATCH", f"/templates/{enc(id_or_name)}", body=body)

    async def delete(self, id_or_name: str) -> None:
        return await self._c._request("DELETE", f"/templates/{enc(id_or_name)}")

    async def versions(self, id_or_name: str) -> "TemplateVersionList":
        return await self._c._request("GET", f"/templates/{enc(id_or_name)}/versions")

    async def preview(
        self,
        id_or_name: str,
        variables: Optional[Mapping[str, Any]] = None,
        *,
        version: Optional[int] = None,
        idempotency_key: Optional[str] = None,
    ) -> "PreviewTemplateResponse":
        """Renders the template with ``variables`` (nothing is sent)."""
        body: Dict[str, Any] = {"variables": dict(variables or {})}
        if version is not None:
            body["version"] = version
        return await self._c._request("POST", f"/templates/{enc(id_or_name)}/preview", body=body, idempotency_key=idempotency_key)


class Contacts(_Resource):
    async def create(self, body: "UpsertContactRequest", *, idempotency_key: Optional[str] = None) -> "Contact":
        """Creates the contact or merges the attributes of the existing one with the same email."""
        return await self._c._request("POST", "/contacts", body=body, idempotency_key=idempotency_key)

    upsert = create

    async def list(self, *, limit: Optional[int] = None, starting_after: Optional[str] = None, q: Optional[str] = None) -> "ContactList":
        return await self._c._request("GET", "/contacts", query={"limit": limit, "starting_after": starting_after, "q": q})

    async def get(self, id_or_email: str) -> "Contact":
        """By id (con_...) or by email."""
        return await self._c._request("GET", f"/contacts/{enc(id_or_email)}")

    async def update(self, id_or_email: str, body: "UpdateContactRequest") -> "Contact":
        return await self._c._request("PATCH", f"/contacts/{enc(id_or_email)}", body=body)

    async def delete(self, id_or_email: str) -> None:
        return await self._c._request("DELETE", f"/contacts/{enc(id_or_email)}")

    def iterate(self, *, q: Optional[str] = None, limit: int = 100) -> AsyncIterator["Contact"]:
        return self._paginate("/contacts", {"limit": limit, "q": q})

    async def count(self, audience: "Audience", *, idempotency_key: Optional[str] = None) -> "AudienceCount":
        """How many contacts match an audience (all, subscribed, suppressed)."""
        return await self._c._request("POST", "/contacts/count", body={"audience": audience}, idempotency_key=idempotency_key)


class Campaigns(_Resource):
    async def create(self, body: "CreateCampaignRequest", *, idempotency_key: Optional[str] = None) -> "Campaign":
        """Creates a draft campaign."""
        return await self._c._request("POST", "/campaigns", body=body, idempotency_key=idempotency_key)

    async def list(self, *, limit: Optional[int] = None, starting_after: Optional[str] = None, status: Optional["CampaignStatus"] = None) -> "CampaignList":
        return await self._c._request("GET", "/campaigns", query={"limit": limit, "starting_after": starting_after, "status": status})

    async def get(self, id: str) -> "Campaign":
        return await self._c._request("GET", f"/campaigns/{enc(id)}")

    async def update(self, id: str, body: "UpdateCampaignRequest") -> "Campaign":
        return await self._c._request("PATCH", f"/campaigns/{enc(id)}", body=body)

    async def delete(self, id: str) -> None:
        return await self._c._request("DELETE", f"/campaigns/{enc(id)}")

    async def preflight(self, id: str, *, idempotency_key: Optional[str] = None) -> "CampaignPreflight":
        """Checks before sending: recipients, warnings and a content review."""
        return await self._c._request("POST", f"/campaigns/{enc(id)}/preflight", idempotency_key=idempotency_key)

    async def send(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return await self._c._request("POST", f"/campaigns/{enc(id)}/send", idempotency_key=idempotency_key)

    async def schedule(self, id: str, scheduled_at: DateLike, *, idempotency_key: Optional[str] = None) -> "Campaign":
        """``scheduled_at``: ISO 8601 string or ``datetime`` (naive datetimes are treated as UTC)."""
        return await self._c._request("POST", f"/campaigns/{enc(id)}/schedule", body={"scheduled_at": to_iso(scheduled_at)}, idempotency_key=idempotency_key)

    async def pause(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return await self._c._request("POST", f"/campaigns/{enc(id)}/pause", idempotency_key=idempotency_key)

    async def resume(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return await self._c._request("POST", f"/campaigns/{enc(id)}/resume", idempotency_key=idempotency_key)

    async def cancel(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return await self._c._request("POST", f"/campaigns/{enc(id)}/cancel", idempotency_key=idempotency_key)

    async def test(self, id: str, to: Optional[Union[str, Sequence[str]]] = None, *, idempotency_key: Optional[str] = None) -> "TestCampaignResponse":
        """Sends a test to people of your account (up to 5 addresses; default: you)."""
        body = {"to": _to_list(to)} if to else {}
        return await self._c._request("POST", f"/campaigns/{enc(id)}/test", body=body, idempotency_key=idempotency_key)

    async def stats(self, id: str) -> "CampaignStats":
        return await self._c._request("GET", f"/campaigns/{enc(id)}/stats")


class AsyncCouryo(BaseClient):
    """Couryo API client (asyncio), with the same resources and options as :class:`~couryo.Couryo`.

    .. code-block:: python

        from couryo import AsyncCouryo

        async with AsyncCouryo() as couryo:
            res = await couryo.emails.send({"from": "Shop <hi@example.com>", "to": "ana@example.com", "subject": "Hi", "text": "Hello!"})

    ``http_client`` takes your own ``httpx.AsyncClient`` (the SDK does not close it).
    """

    _sleep: Callable[[float], Any] = staticmethod(asyncio.sleep)

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        max_retries: int = 2,
        timeout: float = 30.0,
        language: str = "pt-BR",
        http_client: Optional[httpx.AsyncClient] = None,
        _sleep: Optional[Callable[[float], Any]] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, max_retries=max_retries, timeout=timeout, language=language, _sleep=_sleep)
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.AsyncClient()
        self.emails = Emails(self)
        self.domains = Domains(self)
        self.webhooks = Webhooks(self)
        self.suppressions = Suppressions(self)
        self.events = Events(self)
        self.templates = Templates(self)
        self.contacts = Contacts(self)
        self.campaigns = Campaigns(self)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        query: Optional[Mapping[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        flow: Flow = self._flow(method, path, body=body, query=query, idempotency_key=idempotency_key)
        try:
            kind, arg = next(flow)
            while True:
                if kind == "send":
                    try:
                        outcome: Any = await self._http.request(arg.method, arg.url, headers=arg.headers, content=arg.content, timeout=self.timeout)
                    except httpx.TransportError as exc:  # connection errors and timeouts
                        outcome = exc
                    kind, arg = flow.send(outcome)
                else:
                    waited = self._sleep(arg)
                    if inspect.isawaitable(waited):
                        await waited
                    kind, arg = flow.send(None)
        except StopIteration as stop:
            return stop.value

    async def aclose(self) -> None:
        """Closes the HTTP connections (only when the SDK created the ``httpx.AsyncClient``)."""
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncCouryo":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type] = None,
        exc: Optional[BaseException] = None,
        tb: Optional["TracebackType"] = None,
    ) -> None:
        await self.aclose()
