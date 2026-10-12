from __future__ import annotations

import base64
from email.message import MIMEPart
from email.mime.image import MIMEImage

import pytest

django = pytest.importorskip("django")

from django.conf import settings  # noqa: E402

HAS_MAILERS = django.VERSION >= (6, 1)

if not settings.configured:
    mail_settings = (
        {"MAILERS": {"default": {"BACKEND": "couryo.django.EmailBackend"}}}
        if HAS_MAILERS
        else {"EMAIL_BACKEND": "couryo.django.EmailBackend"}
    )
    settings.configure(
        COURYO_API_KEY="ck_test_settings",
        COURYO_BASE_URL="https://api.couryo.com/v1",
        DEFAULT_FROM_EMAIL="Loja <oi@loja.com.br>",
        DEFAULT_CHARSET="utf-8",
        **mail_settings,
    )
    django.setup()

from django.core import mail  # noqa: E402
from django.core.mail import EmailMessage, EmailMultiAlternatives  # noqa: E402
from django.test import override_settings  # noqa: E402

from couryo import InvalidRequestError  # noqa: E402
from couryo.django import EmailBackend, message_to_request  # noqa: E402
from fakes import FakeApi, api_error  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfake"


def inline_png():
    """Inline image: MIMEPart on Django 6.0+ (MIMEBase is deprecated there), MIMEImage before."""
    if django.VERSION >= (6, 0):
        part = MIMEPart()
        part.set_content(PNG, maintype="image", subtype="png", disposition="inline", filename="logo.png", cid="<logo>")
        return part
    img = MIMEImage(PNG, "png")
    img.add_header("Content-ID", "<logo>")
    img.add_header("Content-Disposition", "inline", filename="logo.png")
    return img


def test_backend_converts_a_full_message():
    api = FakeApi([(202, {"id": "msg_dj1", "status": "queued"})])
    backend = EmailBackend(client=api.sync())
    msg = EmailMultiAlternatives(
        subject="Pedido 1042 confirmado",
        body="Obrigado pela compra!",
        from_email="Loja <pedidos@loja.com.br>",
        to=["ana@gmail.com"],
        cc=["financeiro@loja.com.br"],
        bcc=["arquivo@loja.com.br"],
        reply_to=["suporte@loja.com.br"],
        headers={
            "X-Couryo-Stream": "transactional",
            "X-Couryo-Tags": "tipo=pedido, loja=centro",
            "X-Pedido": "1042",
            "Idempotency-Key": "pedido-1042-confirmacao",
            "X-Couryo-Unknown": "dropped",
            "Organization": "dropped too",
        },
    )
    msg.attach_alternative("<p>Obrigado pela compra!</p>", "text/html")
    msg.attach("nota.pdf", b"%PDF-1.4 fake", "application/pdf")
    msg.attach("leia.txt", "Olá", None)
    msg.attach(inline_png())

    assert backend.send_messages([msg]) == 1
    assert msg.couryo_id == "msg_dj1"
    call = api.calls[0]
    assert (call.method, call.path) == ("POST", "/emails")
    assert call.headers["idempotency-key"] == "pedido-1042-confirmacao"
    assert call.json == {
        "from": "Loja <pedidos@loja.com.br>",
        "to": ["ana@gmail.com"],
        "cc": ["financeiro@loja.com.br"],
        "bcc": ["arquivo@loja.com.br"],
        "reply_to": ["suporte@loja.com.br"],
        "subject": "Pedido 1042 confirmado",
        "text": "Obrigado pela compra!",
        "html": "<p>Obrigado pela compra!</p>",
        "attachments": [
            {"filename": "nota.pdf", "content": base64.b64encode(b"%PDF-1.4 fake").decode(), "content_type": "application/pdf"},
            {"filename": "leia.txt", "content": base64.b64encode("Olá".encode()).decode(), "content_type": "text/plain"},
            {"filename": "logo.png", "content": base64.b64encode(PNG).decode(), "content_type": "image/png", "content_id": "logo"},
        ],
        "stream": "transactional",
        "tags": {"tipo": "pedido", "loja": "centro"},
        "headers": {"X-Pedido": "1042"},
    }


def test_html_body_default_from_and_automatic_key():
    msg = EmailMessage("Oi", "<h1>Olá</h1>", to=["ana@gmail.com"], headers={"X-Couryo-Stream": "marketing"})
    msg.content_subtype = "html"
    body, key = message_to_request(msg)
    assert key is None
    assert body == {"from": "Loja <oi@loja.com.br>", "to": ["ana@gmail.com"], "subject": "Oi", "html": "<h1>Olá</h1>", "stream": "marketing"}

    only_bcc = EmailMessage("Oi", "texto", to=[], bcc=["a@x.com", "b@x.com"])
    body, _ = message_to_request(only_bcc)
    assert body["to"] == ["a@x.com"] and body["bcc"] == ["b@x.com"]

    api = FakeApi([(202, {"id": "msg_2", "status": "queued"})])
    EmailBackend(client=api.sync()).send_messages([EmailMessage("Oi", "texto", to=["ana@gmail.com"])])
    assert len(api.calls[0].headers["idempotency-key"]) == 36


@pytest.mark.skipif(HAS_MAILERS, reason="get_connection() and connection= are deprecated in Django 6.1 (MAILERS)")
def test_send_mail_through_a_connection_counts_and_skips_empty():
    api = FakeApi([(202, {"id": "msg_a", "status": "queued"}), (202, {"id": "msg_b", "status": "queued"})])
    connection = mail.get_connection("couryo.django.EmailBackend", client=api.sync())
    assert mail.send_mail("Assunto", "Corpo", None, ["ana@gmail.com"], connection=connection) == 1
    sent = connection.send_messages([EmailMessage("A", "a", to=["x@y.com"]), EmailMessage("vazio", "sem destinatário", to=[])])
    assert sent == 1
    assert len(api.calls) == 2
    assert api.calls[0].json["from"] == "Loja <oi@loja.com.br>"
    assert connection.send_messages([]) == 0


@pytest.mark.skipif(not HAS_MAILERS, reason="MAILERS needs Django 6.1 or newer")
def test_mailers_alias_counts_and_skips_empty():
    """Django 6.1+ path without deprecated APIs: send_mail(using=...), EmailMessage.send(using=...)."""
    api = FakeApi([(202, {"id": "msg_a", "status": "queued"}), (202, {"id": "msg_b", "status": "queued"})])
    mailers = {
        "default": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"client": api.sync()}},
        "news": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"client": api.sync()}},
    }
    with override_settings(MAILERS=mailers):
        assert mail.send_mail("Assunto", "Corpo", None, ["ana@gmail.com"], using="default") == 1
        msg = EmailMessage("A", "a", to=["x@y.com"], headers={"X-Couryo-Stream": "marketing"})
        assert msg.send(using="news") == 1
        assert msg.couryo_id == "msg_b"
        assert EmailMessage("vazio", "sem destinatário", to=[]).send(using="news") == 0
        connection = mail.mailers["news"]
        assert isinstance(connection, EmailBackend) and connection.alias == "news"
        assert connection.send_messages([]) == 0
    assert len(api.calls) == 2
    assert api.calls[0].json["from"] == "Loja <oi@loja.com.br>"
    assert api.calls[1].json["stream"] == "marketing"


@pytest.mark.skipif(not HAS_MAILERS, reason="MAILERS needs Django 6.1 or newer")
def test_mailers_fail_silently_option_and_unknown_options():
    api = FakeApi([api_error(422, "domain_not_verified")])
    mailers = {
        "default": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"client": api.sync(), "fail_silently": True}},
        "typo": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"api_kye": "ck_test_x"}},
    }
    with override_settings(MAILERS=mailers):
        assert mail.send_mail("Oi", "texto", None, ["ana@gmail.com"], using="default") == 0
        # Unknown OPTIONS reach BaseEmailBackend, which reports them with the alias.
        with pytest.raises(mail.InvalidMailer, match="api_kye"):
            mail.mailers["typo"]


def test_fail_silently_and_errors():
    api = FakeApi([api_error(422, "domain_not_verified")])
    loud = EmailBackend(client=api.sync())
    with pytest.raises(InvalidRequestError):
        loud.send_messages([EmailMessage("Oi", "texto", to=["ana@gmail.com"])])
    quiet = EmailBackend(fail_silently=True, client=api.sync())
    assert quiet.send_messages([EmailMessage("Oi", "texto", to=["ana@gmail.com"])]) == 0


def test_settings_and_owned_client(monkeypatch):
    backend = EmailBackend()
    assert backend.api_key == "ck_test_settings"
    assert backend.base_url == "https://api.couryo.com/v1"
    assert backend.open() is True
    assert backend.client is not None and backend.client.base_url == "https://api.couryo.com/v1"
    assert backend.open() is False
    backend.close()
    assert backend.client is None

    monkeypatch.delenv("COURYO_API_KEY", raising=False)
    monkeypatch.setattr(settings, "COURYO_API_KEY", None)
    no_key = EmailBackend(fail_silently=True)
    assert no_key.send_messages([EmailMessage("Oi", "texto", to=["ana@gmail.com"])]) == 0
    with pytest.raises(ValueError, match="missing API key"):
        EmailBackend().send_messages([EmailMessage("Oi", "texto", to=["ana@gmail.com"])])


@pytest.mark.skipif(not HAS_MAILERS, reason="MAILERS needs Django 6.1 or newer")
def test_mailers_options():
    api = FakeApi([(202, {"id": "msg_m", "status": "queued"})])
    mailers = {"default": {"BACKEND": "couryo.django.EmailBackend", "OPTIONS": {"client": api.sync()}}}
    with override_settings(MAILERS=mailers):
        assert mail.send_mail("Oi", "texto", None, ["ana@gmail.com"]) == 1
    assert api.calls[0].json["to"] == ["ana@gmail.com"]
    backend = EmailBackend(alias="default", api_key="ck_test_opt")
    assert backend.alias == "default" and backend.api_key == "ck_test_opt"
