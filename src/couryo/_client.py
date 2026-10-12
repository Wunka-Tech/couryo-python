"""Synchronous client: :class:`Couryo`."""

from __future__ import annotations

import datetime as _dt
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Union

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

__all__ = ["Couryo"]

DateLike = Union[str, _dt.datetime]


def _to_list(value: Union[str, Sequence[str]]) -> List[str]:
    return [value] if isinstance(value, str) else list(value)


class _Resource:
    def __init__(self, client: "Couryo") -> None:
        self._c = client

    def _paginate(self, path: str, query: Dict[str, Any]) -> Iterator[Any]:
        """Walks every page (cursor pagination, newest first)."""
        after: Optional[str] = None
        while True:
            page = self._c._request("GET", path, query={**query, "starting_after": after})
            data = (page or {}).get("data") or []
            for item in data:
                yield item
            if not page or not page.get("has_more") or not data:
                return
            after = data[-1]["id"]


class Emails(_Resource):
    def send(self, body: "SendEmailRequest", *, idempotency_key: Optional[str] = None) -> "SendEmailResponse":
        """Queues one email (202). A POST retried by the SDK reuses the same Idempotency-Key."""
        return self._c._request("POST", "/emails", body=body, idempotency_key=idempotency_key)

    def batch(self, emails: Sequence["SendEmailRequest"], *, idempotency_key: Optional[str] = None) -> "BatchSendResponse":
        """Up to 100 emails; one result per item, in order."""
        return self._c._request("POST", "/emails/batch", body={"emails": list(emails)}, idempotency_key=idempotency_key)

    def check(self, body: "SendEmailRequest", *, idempotency_key: Optional[str] = None) -> "CheckEmailResponse":
        """Checks content and sender before sending (nothing is sent)."""
        return self._c._request("POST", "/emails/check", body=body, idempotency_key=idempotency_key)

    def get(self, id: str) -> "Email":
        return self._c._request("GET", f"/emails/{enc(id)}")

    def list(
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
        return self._c._request("GET", "/emails", query=query)

    def iterate(
        self,
        *,
        status: Optional["EmailStatus"] = None,
        recipient: Optional[str] = None,
        tag: Optional[str] = None,
        period: Optional["Period"] = None,
        limit: int = 100,
    ) -> Iterator["Email"]:
        """``for email in couryo.emails.iterate(status="bounced"): ...``"""
        return self._paginate("/emails", {"limit": limit, "status": status, "recipient": recipient, "tag": tag, "period": period})


class Domains(_Resource):
    def list(self) -> "DomainList":
        return self._c._request("GET", "/domains")

    def create(self, name: str, *, idempotency_key: Optional[str] = None) -> "Domain":
        return self._c._request("POST", "/domains", body={"name": name}, idempotency_key=idempotency_key)

    def get(self, id: str) -> "Domain":
        return self._c._request("GET", f"/domains/{enc(id)}")

    def delete(self, id: str) -> None:
        return self._c._request("DELETE", f"/domains/{enc(id)}")

    def verify(self, id: str, *, idempotency_key: Optional[str] = None) -> "Domain":
        return self._c._request("POST", f"/domains/{enc(id)}/verify", idempotency_key=idempotency_key)

    def health(self, id: str, *, refresh: bool = False) -> "DomainHealth":
        """Deliverability diagnosis (read only). ``refresh=True`` runs every check now."""
        return self._c._request("GET", f"/domains/{enc(id)}/health", query={"refresh": 1} if refresh else None)


class Webhooks(_Resource):
    def list(self) -> "WebhookList":
        return self._c._request("GET", "/webhooks")

    def create(self, body: "CreateWebhookRequest", *, idempotency_key: Optional[str] = None) -> "Webhook":
        """The secret (whsec_...) comes back only here: store it."""
        return self._c._request("POST", "/webhooks", body=body, idempotency_key=idempotency_key)

    def get(self, id: str) -> "Webhook":
        return self._c._request("GET", f"/webhooks/{enc(id)}")

    def update(self, id: str, body: "UpdateWebhookRequest") -> "Webhook":
        return self._c._request("PATCH", f"/webhooks/{enc(id)}", body=body)

    def delete(self, id: str) -> None:
        return self._c._request("DELETE", f"/webhooks/{enc(id)}")


class Suppressions(_Resource):
    def list(
        self,
        *,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
        q: Optional[str] = None,
        reason: Optional["SuppressionReason"] = None,
    ) -> "SuppressionList":
        return self._c._request("GET", "/suppressions", query={"limit": limit, "starting_after": starting_after, "q": q, "reason": reason})

    def add(self, email: str, *, stream: "SuppressionStream" = "all", idempotency_key: Optional[str] = None) -> "Suppression":
        return self._c._request("POST", "/suppressions", body={"email": email, "stream": stream}, idempotency_key=idempotency_key)

    def remove(self, email: str) -> None:
        return self._c._request("DELETE", f"/suppressions/{enc(email)}")


class Events(_Resource):
    def list(
        self,
        *,
        limit: Optional[int] = None,
        starting_after: Optional[str] = None,
        type: Optional["EmailEventType"] = None,
        email_id: Optional[str] = None,
    ) -> "EmailEventList":
        """Email delivery events (for whoever missed a webhook)."""
        return self._c._request("GET", "/events", query={"limit": limit, "starting_after": starting_after, "type": type, "email_id": email_id})

    def iterate(self, *, type: Optional["EmailEventType"] = None, email_id: Optional[str] = None, limit: int = 100) -> Iterator["EmailEvent"]:
        return self._paginate("/events", {"limit": limit, "type": type, "email_id": email_id})

    def track(self, body: "TrackEventRequest", *, idempotency_key: Optional[str] = None) -> "TrackEventResponse":
        """Records a contact event (``user.signed_up``, ``order.paid``...): it can start sequences (201)."""
        return self._c._request("POST", "/events", body=body, idempotency_key=idempotency_key)


class Templates(_Resource):
    def list(self) -> "TemplateList":
        return self._c._request("GET", "/templates")

    def create(self, body: "CreateTemplateRequest", *, idempotency_key: Optional[str] = None) -> "Template":
        return self._c._request("POST", "/templates", body=body, idempotency_key=idempotency_key)

    def get(self, id_or_name: str) -> "Template":
        """By id (tpl_...) or by name."""
        return self._c._request("GET", f"/templates/{enc(id_or_name)}")

    def update(self, id_or_name: str, body: "UpdateTemplateRequest") -> "Template":
        """Content changes create a new version."""
        return self._c._request("PATCH", f"/templates/{enc(id_or_name)}", body=body)

    def delete(self, id_or_name: str) -> None:
        return self._c._request("DELETE", f"/templates/{enc(id_or_name)}")

    def versions(self, id_or_name: str) -> "TemplateVersionList":
        return self._c._request("GET", f"/templates/{enc(id_or_name)}/versions")

    def preview(
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
        return self._c._request("POST", f"/templates/{enc(id_or_name)}/preview", body=body, idempotency_key=idempotency_key)


class Contacts(_Resource):
    def create(self, body: "UpsertContactRequest", *, idempotency_key: Optional[str] = None) -> "Contact":
        """Creates the contact or merges the attributes of the existing one with the same email."""
        return self._c._request("POST", "/contacts", body=body, idempotency_key=idempotency_key)

    upsert = create

    def list(self, *, limit: Optional[int] = None, starting_after: Optional[str] = None, q: Optional[str] = None) -> "ContactList":
        return self._c._request("GET", "/contacts", query={"limit": limit, "starting_after": starting_after, "q": q})

    def get(self, id_or_email: str) -> "Contact":
        """By id (con_...) or by email."""
        return self._c._request("GET", f"/contacts/{enc(id_or_email)}")

    def update(self, id_or_email: str, body: "UpdateContactRequest") -> "Contact":
        return self._c._request("PATCH", f"/contacts/{enc(id_or_email)}", body=body)

    def delete(self, id_or_email: str) -> None:
        return self._c._request("DELETE", f"/contacts/{enc(id_or_email)}")

    def iterate(self, *, q: Optional[str] = None, limit: int = 100) -> Iterator["Contact"]:
        return self._paginate("/contacts", {"limit": limit, "q": q})

    def count(self, audience: "Audience", *, idempotency_key: Optional[str] = None) -> "AudienceCount":
        """How many contacts match an audience (all, subscribed, suppressed)."""
        return self._c._request("POST", "/contacts/count", body={"audience": audience}, idempotency_key=idempotency_key)


class Campaigns(_Resource):
    def create(self, body: "CreateCampaignRequest", *, idempotency_key: Optional[str] = None) -> "Campaign":
        """Creates a draft campaign."""
        return self._c._request("POST", "/campaigns", body=body, idempotency_key=idempotency_key)

    def list(self, *, limit: Optional[int] = None, starting_after: Optional[str] = None, status: Optional["CampaignStatus"] = None) -> "CampaignList":
        return self._c._request("GET", "/campaigns", query={"limit": limit, "starting_after": starting_after, "status": status})

    def get(self, id: str) -> "Campaign":
        return self._c._request("GET", f"/campaigns/{enc(id)}")

    def update(self, id: str, body: "UpdateCampaignRequest") -> "Campaign":
        return self._c._request("PATCH", f"/campaigns/{enc(id)}", body=body)

    def delete(self, id: str) -> None:
        return self._c._request("DELETE", f"/campaigns/{enc(id)}")

    def preflight(self, id: str, *, idempotency_key: Optional[str] = None) -> "CampaignPreflight":
        """Checks before sending: recipients, warnings and a content review."""
        return self._c._request("POST", f"/campaigns/{enc(id)}/preflight", idempotency_key=idempotency_key)

    def send(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return self._c._request("POST", f"/campaigns/{enc(id)}/send", idempotency_key=idempotency_key)

    def schedule(self, id: str, scheduled_at: DateLike, *, idempotency_key: Optional[str] = None) -> "Campaign":
        """``scheduled_at``: ISO 8601 string or ``datetime`` (naive datetimes are treated as UTC)."""
        return self._c._request("POST", f"/campaigns/{enc(id)}/schedule", body={"scheduled_at": to_iso(scheduled_at)}, idempotency_key=idempotency_key)

    def pause(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return self._c._request("POST", f"/campaigns/{enc(id)}/pause", idempotency_key=idempotency_key)

    def resume(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return self._c._request("POST", f"/campaigns/{enc(id)}/resume", idempotency_key=idempotency_key)

    def cancel(self, id: str, *, idempotency_key: Optional[str] = None) -> "Campaign":
        return self._c._request("POST", f"/campaigns/{enc(id)}/cancel", idempotency_key=idempotency_key)

    def test(self, id: str, to: Optional[Union[str, Sequence[str]]] = None, *, idempotency_key: Optional[str] = None) -> "TestCampaignResponse":
        """Sends a test to people of your account (up to 5 addresses; default: you)."""
        body = {"to": _to_list(to)} if to else {}
        return self._c._request("POST", f"/campaigns/{enc(id)}/test", body=body, idempotency_key=idempotency_key)

    def stats(self, id: str) -> "CampaignStats":
        return self._c._request("GET", f"/campaigns/{enc(id)}/stats")


class Couryo(BaseClient):
    """Couryo API client (synchronous).

    .. code-block:: python

        from couryo import Couryo

        couryo = Couryo()  # reads COURYO_API_KEY
        res = couryo.emails.send({"from": "Shop <hi@example.com>", "to": "ana@example.com", "subject": "Hi", "text": "Hello!"})

    Options: ``api_key`` (default ``COURYO_API_KEY``), ``base_url``, ``max_retries`` (2),
    ``timeout`` (30 s per attempt), ``language`` (``"pt-BR"`` or ``"en"``, for error messages)
    and ``http_client`` (your own ``httpx.Client``; the SDK does not close it).
    """

    _sleep: Callable[[float], Any] = staticmethod(time.sleep)

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        max_retries: int = 2,
        timeout: float = 30.0,
        language: str = "pt-BR",
        http_client: Optional[httpx.Client] = None,
        _sleep: Optional[Callable[[float], Any]] = None,
    ) -> None:
        super().__init__(api_key, base_url=base_url, max_retries=max_retries, timeout=timeout, language=language, _sleep=_sleep)
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.Client()
        self.emails = Emails(self)
        self.domains = Domains(self)
        self.webhooks = Webhooks(self)
        self.suppressions = Suppressions(self)
        self.events = Events(self)
        self.templates = Templates(self)
        self.contacts = Contacts(self)
        self.campaigns = Campaigns(self)

    def _request(
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
                        outcome: Any = self._http.request(arg.method, arg.url, headers=arg.headers, content=arg.content, timeout=self.timeout)
                    except httpx.TransportError as exc:  # connection errors and timeouts
                        outcome = exc
                    kind, arg = flow.send(outcome)
                else:
                    self._sleep(arg)
                    kind, arg = flow.send(None)
        except StopIteration as stop:
            return stop.value

    def close(self) -> None:
        """Closes the HTTP connections (only when the SDK created the ``httpx.Client``)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "Couryo":
        return self

    def __exit__(
        self,
        exc_type: Optional[type] = None,
        exc: Optional[BaseException] = None,
        tb: Optional["TracebackType"] = None,
    ) -> None:
        self.close()
