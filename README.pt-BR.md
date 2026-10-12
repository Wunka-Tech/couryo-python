# couryo (Python)

SDK oficial em Python da API de e-mail do [Couryo](https://couryo.com). [Read in English](./README.md).

- Cliente síncrono (`Couryo`) e assíncrono (`AsyncCouryo`) sobre o `httpx`, a única dependência.
- Tipos saem do contrato da API: `TypedDict`s em `couryo.types` para pedidos e respostas (em tempo de execução, dicts comuns).
- `Idempotency-Key` automático em todo POST, repetido nas novas tentativas: um envio que deu tempo esgotado mas passou nunca sai duplicado.
- Novas tentativas com espera crescente para erro de rede, `5xx` e `rate_limited` (respeita o `Retry-After`). Erros que falhariam de novo (`domain_not_verified`, `daily_limit_reached`...) voltam na hora.
- Verificação de webhook (Standard Webhooks) numa chamada.
- Backend de e-mail para Django (`couryo.django.EmailBackend`).
- Python 3.9 ou mais novo.

> Ainda não está no PyPI. Dentro do monorepo do Couryo, fica em `packages/sdk-python` (`pip install -e packages/sdk-python`).

## Instalar

```bash
pip install couryo
# com o backend do Django
pip install "couryo[django]"
```

## Enviar um e-mail

```python
import os
from couryo import Couryo

couryo = Couryo(api_key=os.environ["COURYO_API_KEY"])  # ck_live_... ou ck_test_... (por padrão já lê COURYO_API_KEY)

res = couryo.emails.send({
    "from": "Loja <pedidos@exemplo.com.br>",
    "to": "ana@exemplo.com.br",
    "subject": "Pedido 1042 confirmado",
    "html": "<p>Obrigado!</p>",
    "text": "Obrigado!",
    "tags": {"tipo": "pedido"},
})
print(res["id"], res["status"])
```

O `Couryo` funciona como gerenciador de contexto (`with Couryo() as couryo: ...`) ou pode ser fechado com `couryo.close()`.

### Assíncrono

```python
import asyncio
from couryo import AsyncCouryo

async def main():
    async with AsyncCouryo() as couryo:
        res = await couryo.emails.send({"from": "Loja <pedidos@exemplo.com.br>", "to": "ana@exemplo.com.br", "subject": "Oi", "text": "Olá!"})
        async for email in couryo.emails.iterate(status="bounced"):
            print(email["id"])

asyncio.run(main())
```

Fora do `async with`, chame `await couryo.aclose()` no fim.

## Idempotência

Todo POST leva um `Idempotency-Key` (um UUID aleatório), repetido em cada nova tentativa. Passe a sua própria chave quando o mesmo evento do seu sistema puder disparar duas vezes:

```python
couryo.emails.send(corpo, idempotency_key="pedido-1042-confirmacao")
```

## Templates salvos

```python
couryo.templates.create({"name": "boas-vindas", "subject": "Bem-vinda, {{nome}}!", "html": "<h1>Olá, {{nome}}</h1>"})
couryo.emails.send({"from": "Loja <oi@exemplo.com.br>", "to": "ana@exemplo.com.br", "template": "boas-vindas", "variables": {"nome": "Ana"}})
```

## Contatos, eventos e campanhas

```python
# Cria ou atualiza um contato (mesmo e-mail = junta os atributos)
couryo.contacts.create({"email": "ana@exemplo.com.br", "attributes": {"plano": "pro"}, "tags": ["cliente"]})

# Um evento do contato pode iniciar sequências
couryo.events.track(
    {"contact": {"email": "ana@exemplo.com.br"}, "name": "order.paid", "properties": {"total": 99.9}},
    idempotency_key="pedido-1042-pago",
)

# Uma campanha para um segmento
publico = {"type": "segment", "conditions": [{"field": "tag", "op": "eq", "value": "cliente"}]}
print(couryo.contacts.count(publico))
campanha = couryo.campaigns.create({
    "name": "Novidades de outubro",
    "audience": publico,
    "from": "Loja <novidades@exemplo.com.br>",
    "subject": "O que chegou em outubro",
    "html": "<p>Oi!</p>",
})
checagem = couryo.campaigns.preflight(campanha["id"])
if checagem["can_send"]:
    couryo.campaigns.schedule(campanha["id"], "2026-10-20T09:00:00-03:00")  # ou um datetime
```

## Erros

```python
from couryo import CouryoError, InvalidRequestError, RateLimitError

try:
    couryo.emails.send(corpo)
except InvalidRequestError as e:
    print(e.code, e.param)  # ex.: domain_not_verified, from
except CouryoError as e:
    print(e.status, e.type, e.code, e.message, e.param, e.doc_url, e.request_id, e.retry_after)
```

As subclasses seguem o `type` do erro: `InvalidRequestError`, `AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `ConflictError`, `RateLimitError`, `TierLimitError`, `APIError` e `NetworkError` (sem resposta, `status` 0). A `message` segue a opção `language` (`pt-BR` por padrão, ou `en`). Sem chave de API, criar o cliente lança `ValueError`.

## Webhooks

Use o corpo cru, exatamente como chegou. `verify_webhook` devolve o evento (`{type, timestamp, data}`) ou lança `WebhookVerificationError` quando a assinatura não bate ou o horário tem mais de 5 minutos.

Flask:

```python
import os
from flask import Flask, request
from couryo import verify_webhook, WebhookVerificationError

app = Flask(__name__)

@app.post("/webhooks/couryo")
def webhook_couryo():
    try:
        evento = verify_webhook(os.environ["COURYO_WEBHOOK_SECRET"], request.headers, request.get_data())
    except WebhookVerificationError:
        return "", 400
    if evento["type"] == "bounced":
        ...  # evento["data"]["email_id"], evento["data"]["recipient"], evento["data"]["explanation"]
    return "", 200
```

FastAPI:

```python
import os
from fastapi import FastAPI, HTTPException, Request
from couryo import verify_webhook, WebhookVerificationError

app = FastAPI()

@app.post("/webhooks/couryo")
async def webhook_couryo(request: Request):
    try:
        evento = verify_webhook(os.environ["COURYO_WEBHOOK_SECRET"], request.headers, await request.body())
    except WebhookVerificationError:
        raise HTTPException(status_code=400)
    return {"ok": True}
```

Django (vale `request.headers` ou `request.META`):

```python
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from couryo import verify_webhook, WebhookVerificationError

@csrf_exempt
@require_POST
def webhook_couryo(request):
    try:
        evento = verify_webhook(settings.COURYO_WEBHOOK_SECRET, request.headers, request.body)
    except WebhookVerificationError:
        return HttpResponseBadRequest()
    return HttpResponse(status=200)
```

## Backend de e-mail do Django

No Django 6.1 ou mais novo, configure em `MAILERS` (as opções `api_key`, `base_url`, `client` e `fail_silently` vão em `OPTIONS`):

```python
# settings.py
import os

MAILERS = {
    "default": {
        "BACKEND": "couryo.django.EmailBackend",
        "OPTIONS": {"api_key": os.environ["COURYO_API_KEY"]},  # sem ela: a configuração ou a variável de ambiente COURYO_API_KEY
    },
}
DEFAULT_FROM_EMAIL = "Loja <oi@exemplo.com.br>"
```

Com mais de uma entrada em `MAILERS`, escolha com `send_mail(..., using="apelido")` ou `msg.send(using="apelido")`.

No Django 6.0 ou mais antigo, use `EMAIL_BACKEND` (o Django 6.1 ainda aceita, com aviso de descontinuação, mas não junto com `MAILERS`):

```python
# settings.py
import os

EMAIL_BACKEND = "couryo.django.EmailBackend"
COURYO_API_KEY = os.environ["COURYO_API_KEY"]  # sem ele, usa a variável de ambiente COURYO_API_KEY
# COURYO_BASE_URL = "https://api.couryo.com/v1"  # opcional
DEFAULT_FROM_EMAIL = "Loja <oi@exemplo.com.br>"
```

Daí `send_mail`, `EmailMessage` e `EmailMultiAlternatives` passam pela API: um `emails.send` por mensagem, com `from_email`, `to`, `cc`, `bcc`, `reply_to`, `subject`, o corpo (texto, ou HTML quando `content_subtype = "html"`), a alternativa `text/html` e os anexos (Base64; imagens com `Content-ID` viram inline). Cabeçalhos:

- `X-Couryo-Stream: marketing` (ou `transactional`, o padrão);
- `X-Couryo-Tags: tipo=pedido, loja=centro`;
- `Idempotency-Key: pedido-1042` (sem ele, um é gerado);
- os outros cabeçalhos `X-*` são repassados.

O id de cada mensagem enviada fica em `message.couryo_id`. O `fail_silently` é respeitado (no Django 6.1, como opção em `OPTIONS`) e `send_messages` devolve quantas mensagens foram aceitas.

```python
from django.core.mail import EmailMultiAlternatives

msg = EmailMultiAlternatives("Pedido 1042 confirmado", "Obrigado!", to=["ana@exemplo.com.br"], headers={"X-Couryo-Tags": "tipo=pedido"})
msg.attach_alternative("<p>Obrigado!</p>", "text/html")
msg.send()
print(msg.couryo_id)
```

### Ou SMTP, sem o SDK

O backend SMTP do próprio Django também funciona com o Couryo (com os mesmos cabeçalhos `X-Couryo-Stream` e `X-Couryo-Tags`). No Django 6.1 ou mais novo:

```python
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": "smtp.couryo.com",
            "port": 587,  # STARTTLS (a 2525 também usa STARTTLS; a 465 é TLS direto com "use_ssl": True no lugar de "use_tls")
            "username": "couryo",
            "password": os.environ["COURYO_API_KEY"],  # chave com escopo send ou admin
            "use_tls": True,
        },
    },
}
```

No Django 6.0 ou mais antigo:

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.couryo.com"
EMAIL_PORT = 587  # STARTTLS (a 2525 também usa STARTTLS; a 465 é TLS direto com EMAIL_USE_SSL = True)
EMAIL_HOST_USER = "couryo"
EMAIL_HOST_PASSWORD = os.environ["COURYO_API_KEY"]  # chave com escopo send ou admin
EMAIL_USE_TLS = True
```

## Todo o resto

| Recurso | Métodos |
|---|---|
| `emails` | `send`, `batch` (até 100), `check`, `get`, `list`, `iterate` |
| `domains` | `list`, `create`, `get`, `delete`, `verify`, `health` (diagnóstico de entregabilidade, `refresh=True`) |
| `webhooks` | `list`, `create`, `get`, `update`, `delete` |
| `suppressions` | `list`, `add(email, stream="all")`, `remove` |
| `events` | `list`, `iterate` (eventos de entrega), `track` (evento de contato) |
| `templates` | `list`, `create`, `get`, `update`, `delete`, `versions`, `preview(id_ou_nome, variables)` |
| `contacts` | `create` (upsert), `list`, `get` (id ou e-mail), `update`, `delete`, `iterate`, `count(audience)` |
| `campaigns` | `create`, `list`, `get`, `update`, `delete`, `preflight`, `send`, `schedule`, `pause`, `resume`, `cancel`, `test(id, to=None)`, `stats` |

Todo método POST aceita `idempotency_key=`. `iterate` percorre todas as páginas: `for email in couryo.emails.iterate(status="bounced"): ...` (`async for` no `AsyncCouryo`).

Opções: `api_key`, `base_url`, `max_retries` (2), `timeout` (30 s por tentativa), `language`, `http_client` (o seu próprio `httpx.Client` ou `httpx.AsyncClient`, que o SDK não fecha).

Docs: https://couryo.com/docs
