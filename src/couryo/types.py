"""Request and response shapes of the Couryo API, as ``TypedDict``s.

They only describe plain dicts: the SDK sends and returns ``dict`` objects, so these types are
for editors and type checkers. Field names follow the API contract (snake_case). Keys that may
be missing are declared in ``total=False`` dicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

__all__ = [
    "Stream",
    "EmailStatus",
    "EmailEventType",
    "Period",
    "Provider",
    "Attachment",
    "PersonalizeOptions",
    "SendEmailRequest",
    "SendEmailResponse",
    "ErrorBody",
    "ErrorResponse",
    "BatchSendResponse",
    "CheckIssue",
    "CheckEmailResponse",
    "EmailEvent",
    "Email",
    "EmailList",
    "EmailEventList",
    "DnsRecord",
    "Domain",
    "DomainList",
    "DomainHealth",
    "Webhook",
    "WebhookList",
    "CreateWebhookRequest",
    "UpdateWebhookRequest",
    "Suppression",
    "SuppressionList",
    "SuppressionReason",
    "SuppressionStream",
    "Template",
    "TemplateList",
    "TemplateVersion",
    "TemplateVersionList",
    "CreateTemplateRequest",
    "UpdateTemplateRequest",
    "PreviewTemplateRequest",
    "PreviewTemplateResponse",
    "Contact",
    "ContactList",
    "UpsertContactRequest",
    "UpdateContactRequest",
    "TrackEventContact",
    "TrackEventRequest",
    "TrackEventResponse",
    "SegmentCondition",
    "Audience",
    "AudienceCount",
    "CampaignStatus",
    "Campaign",
    "CampaignList",
    "CreateCampaignRequest",
    "UpdateCampaignRequest",
    "CampaignWarning",
    "CampaignPreflight",
    "CampaignStats",
    "TestCampaignResponse",
    "WebhookPayloadData",
    "WebhookPayload",
]

# Enums

Stream = Literal["transactional", "marketing"]
EmailStatus = Literal["queued", "sent", "delivered", "deferred", "bounced", "complained", "failed", "suppressed", "captured"]
EmailEventType = Literal[
    "accepted", "queued", "sent", "delivered", "deferred", "bounced", "complained", "opened", "clicked", "suppressed", "failed", "ai_fallback"
]
Period = Literal["24h", "7d", "30d"]
Provider = Literal["gmail", "microsoft", "yahoo", "uol", "bol", "terra", "locaweb", "other"]
SuppressionReason = Literal["hard_bounce", "complaint", "unsubscribe", "manual"]
SuppressionStream = Literal["transactional", "marketing", "all"]
CampaignStatus = Literal["draft", "scheduled", "in_review", "sending", "paused", "sent", "cancelled"]

# Emails


class _AttachmentRequired(TypedDict):
    filename: str
    content: str  # Base64


class Attachment(_AttachmentRequired, total=False):
    content_type: str
    content_id: str  # inline images: referenced in the HTML as cid:<content_id>


class _PersonalizeRequired(TypedDict):
    instructions: str


class PersonalizeOptions(_PersonalizeRequired, total=False):
    fields: List[str]


# "from" is a Python keyword, so these use the functional syntax.
_SendEmailRequired = TypedDict("_SendEmailRequired", {"from": str, "to": Union[str, List[str]]})


class SendEmailRequest(_SendEmailRequired, total=False):
    cc: Union[str, List[str]]
    bcc: Union[str, List[str]]
    reply_to: Union[str, List[str]]
    subject: str
    html: str
    text: str
    template: str
    variables: Dict[str, Any]
    personalize: PersonalizeOptions
    attachments: List[Attachment]
    headers: Dict[str, str]
    tags: Dict[str, str]
    metadata: Dict[str, str]
    scheduled_at: str
    stream: Stream


class SendEmailResponse(TypedDict):
    id: str
    status: Literal["queued", "captured"]


class _ErrorBodyRequired(TypedDict):
    type: str
    code: str
    message: str
    doc_url: str
    request_id: str


class ErrorBody(_ErrorBodyRequired, total=False):
    param: str
    upgrade_options: List[Dict[str, Any]]


class ErrorResponse(TypedDict):
    error: ErrorBody


class BatchSendResponse(TypedDict):
    data: List[Union[SendEmailResponse, ErrorResponse]]


class CheckIssue(TypedDict):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str


class CheckEmailResponse(TypedDict):
    score: int
    issues: List[CheckIssue]


class _EmailEventRequired(TypedDict):
    id: str
    type: EmailEventType
    at: str


class EmailEvent(_EmailEventRequired, total=False):
    email_id: str
    recipient: str
    mx: str
    provider: Provider
    smtp_code: str
    smtp_response: str
    explanation: str
    url: str
    count: int
    machine: bool


_EmailRequired = TypedDict(
    "_EmailRequired",
    {
        "id": str,
        "project_id": str,
        "from": str,
        "to": List[str],
        "subject": str,
        "stream": Stream,
        "status": EmailStatus,
        "tags": Dict[str, str],
        "metadata": Dict[str, str],
        "created_at": str,
    },
)


class Email(_EmailRequired, total=False):
    cc: List[str]
    bcc: List[str]
    reply_to: List[str]
    scheduled_at: str
    template: Dict[str, Any]
    events: List[EmailEvent]


class EmailList(TypedDict):
    data: List[Email]
    has_more: bool


class EmailEventList(TypedDict):
    data: List[EmailEvent]
    has_more: bool


# Domains


class _DnsRecordRequired(TypedDict):
    purpose: Literal["dkim", "spf", "return_path", "dmarc", "inbound"]
    type: Literal["TXT", "CNAME", "MX"]
    name: str
    value: str
    status: Literal["pending", "ok", "wrong"]


class DnsRecord(_DnsRecordRequired, total=False):
    priority: int
    found: str


class _DomainRequired(TypedDict):
    id: str
    name: str
    status: Literal["pending", "verified", "failed"]
    dmarc_policy: Literal["none", "quarantine", "reject", "missing"]
    records: List[DnsRecord]
    cloudflare_connected: bool
    created_at: str


class Domain(_DomainRequired, total=False):
    verified_at: str


class DomainList(TypedDict):
    data: List[Domain]
    has_more: bool


class DomainHealth(TypedDict, total=False):
    """Deliverability diagnosis of a domain (read only). Nested objects are kept loose."""

    domain_id: str
    domain: str
    status: Literal["good", "attention", "critical"]
    summary: str
    checked_at: str
    authentication: Dict[str, Any]
    blocklists: List[Dict[str, Any]]
    delivery: Dict[str, Any]
    reputation: List[Dict[str, Any]]
    dmarc_suggestion: Optional[Dict[str, Any]]
    findings: List[Dict[str, Any]]


# Webhooks


class _WebhookRequired(TypedDict):
    id: str
    url: str
    events: List[EmailEventType]
    enabled: bool
    created_at: str


class Webhook(_WebhookRequired, total=False):
    secret: str  # whsec_..., returned only on creation
    last_delivery: Dict[str, Any]


class WebhookList(TypedDict):
    data: List[Webhook]
    has_more: bool


class CreateWebhookRequest(TypedDict):
    url: str
    events: List[EmailEventType]


class UpdateWebhookRequest(TypedDict, total=False):
    url: str
    events: List[EmailEventType]
    enabled: bool


# Suppressions


class Suppression(TypedDict):
    email: str
    reason: SuppressionReason
    stream: SuppressionStream
    created_at: str


class SuppressionList(TypedDict):
    data: List[Suppression]
    has_more: bool


# Templates


class _TemplateRequired(TypedDict):
    id: str
    name: str
    format: Literal["html", "mjml"]
    version: int
    subject: str
    html: str
    text: Optional[str]
    variables: List[str]
    created_at: str
    updated_at: str


class Template(_TemplateRequired, total=False):
    editor: Optional[Dict[str, Any]]


class TemplateList(TypedDict):
    data: List[Template]
    has_more: bool


class _TemplateVersionRequired(TypedDict):
    version: int
    subject: str
    html: str
    text: Optional[str]
    variables: List[str]
    created_at: str


class TemplateVersion(_TemplateVersionRequired, total=False):
    editor: Optional[Dict[str, Any]]


class TemplateVersionList(TypedDict):
    data: List[TemplateVersion]
    has_more: bool


class _CreateTemplateRequired(TypedDict):
    name: str
    subject: str
    html: str


class CreateTemplateRequest(_CreateTemplateRequired, total=False):
    format: Literal["html", "mjml"]
    text: str
    editor: Optional[Dict[str, Any]]


class UpdateTemplateRequest(TypedDict, total=False):
    name: str
    subject: str
    html: str
    text: Optional[str]
    editor: Optional[Dict[str, Any]]


class PreviewTemplateRequest(TypedDict, total=False):
    variables: Dict[str, Any]
    version: int


class PreviewTemplateResponse(TypedDict):
    version: int
    subject: str
    html: str
    text: str
    missing_variables: List[str]


# Contacts and contact events


class Contact(TypedDict):
    id: str
    email: str
    attributes: Dict[str, Union[str, int, float, bool]]
    tags: List[str]
    subscribed: bool
    created_at: str
    updated_at: str


class ContactList(TypedDict):
    data: List[Contact]
    has_more: bool


class _UpsertContactRequired(TypedDict):
    email: str


class UpsertContactRequest(_UpsertContactRequired, total=False):
    attributes: Dict[str, Union[str, int, float, bool, None]]
    tags: List[str]


class UpdateContactRequest(TypedDict, total=False):
    email: str
    attributes: Dict[str, Union[str, int, float, bool, None]]
    tags: List[str]


class _TrackEventContactRequired(TypedDict):
    email: str


class TrackEventContact(_TrackEventContactRequired, total=False):
    attributes: Dict[str, Union[str, int, float, bool, None]]


class _TrackEventRequired(TypedDict):
    contact: TrackEventContact
    name: str


class TrackEventRequest(_TrackEventRequired, total=False):
    properties: Dict[str, Any]


class TrackEventResponse(TypedDict):
    id: str
    contact_id: str
    name: str
    enrolled: List[Dict[str, str]]
    converted: List[str]
    created_at: str


# Campaigns


class _SegmentConditionRequired(TypedDict):
    field: Literal["attribute", "tag", "email"]
    op: Literal["eq", "neq", "contains", "exists"]


class SegmentCondition(_SegmentConditionRequired, total=False):
    key: str
    value: str


class _AudienceRequired(TypedDict):
    type: Literal["all", "segment"]


class Audience(_AudienceRequired, total=False):
    match: Literal["all", "any"]
    conditions: List[SegmentCondition]


class AudienceCount(TypedDict):
    total: int
    subscribed: int
    suppressed: int


_CampaignRequired = TypedDict(
    "_CampaignRequired",
    {
        "id": str,
        "name": str,
        "status": CampaignStatus,
        "audience": Audience,
        "from": Optional[str],
        "reply_to": Optional[str],
        "subject": Optional[str],
        "html": Optional[str],
        "text": Optional[str],
        "editor": Optional[Dict[str, Any]],
        "template_id": Optional[str],
        "variables": Dict[str, str],
        "scheduled_at": Optional[str],
        "started_at": Optional[str],
        "finished_at": Optional[str],
        "cancelled_at": Optional[str],
        "paused_reason": Optional[str],
        "status_message": Optional[str],
        "review": Optional[Dict[str, Any]],
        "recipients": Optional[int],
        "progress": Dict[str, int],
        "created_at": str,
        "updated_at": str,
    },
)


class Campaign(_CampaignRequired):
    pass


class CampaignList(TypedDict):
    data: List[Campaign]
    has_more: bool


_CampaignFields = TypedDict(
    "_CampaignFields",
    {
        "name": str,
        "audience": Audience,
        "from": Optional[str],
        "reply_to": Optional[str],
        "subject": Optional[str],
        "html": Optional[str],
        "text": Optional[str],
        "editor": Optional[Dict[str, Any]],
        "template_id": Optional[str],
        "variables": Dict[str, str],
    },
    total=False,
)


class CreateCampaignRequest(_CampaignFields, total=False):
    """``name`` is required; ``audience`` defaults to ``{"type": "all"}``."""


class UpdateCampaignRequest(_CampaignFields, total=False):
    pass


class CampaignWarning(TypedDict):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str


class CampaignPreflight(TypedDict):
    recipients: int
    suppressed: int
    never_emailed: int
    never_emailed_share: float
    needs_review: bool
    can_send: bool
    warnings: List[CampaignWarning]
    review: Optional[Dict[str, Any]]


class CampaignStats(TypedDict, total=False):
    campaign_id: str
    recipients: int
    sent: int
    delivered: int
    bounced: int
    complained: int
    opened: int
    opened_machine: int
    clicked: int
    unsubscribed: int
    skipped: int
    failed: int
    rates: Dict[str, float]
    top_links: List[Dict[str, Any]]
    opens_estimated: bool


class TestCampaignResponse(TypedDict):
    data: List[Dict[str, str]]


# Webhook payload


class _WebhookPayloadDataRequired(TypedDict):
    email_id: str
    event_id: str
    tags: Dict[str, str]
    metadata: Dict[str, str]


class WebhookPayloadData(_WebhookPayloadDataRequired, total=False):
    recipient: str
    provider: Provider
    mx: str
    smtp_code: str
    smtp_response: str
    explanation: str
    url: str
    machine: bool


class WebhookPayload(TypedDict):
    type: EmailEventType
    timestamp: str
    data: WebhookPayloadData
