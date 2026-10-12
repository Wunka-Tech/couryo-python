"""Test doubles: a fake Couryo API on httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx

from couryo import AsyncCouryo, Couryo

Answer = Union[BaseException, tuple]


class Call:
    def __init__(self, request: httpx.Request) -> None:
        self.method = request.method
        self.url = str(request.url)
        self.path = self.url.replace("https://api.couryo.com/v1", "")
        self.headers: Dict[str, str] = {k.lower(): v for k, v in request.headers.items()}
        self.content = request.content

    @property
    def json(self) -> Any:
        return json.loads(self.content) if self.content else None

    def __repr__(self) -> str:
        return f"<Call {self.method} {self.path}>"


class FakeApi:
    """Answers in order (the last answer repeats) and records every call."""

    def __init__(self, answers: Sequence[Answer]) -> None:
        self.answers = list(answers)
        self.calls: List[Call] = []
        self.sleeps: List[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(Call(request))
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        status, body, *rest = answer
        headers = rest[0] if rest else {}
        if status == 204:
            return httpx.Response(204, headers=headers)
        if isinstance(body, (str, bytes)):
            return httpx.Response(status, content=body, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def sync(self, **opts: Any) -> Couryo:
        opts.setdefault("api_key", "ck_test_abc")
        return Couryo(http_client=httpx.Client(transport=self.transport), _sleep=self.sleeps.append, **opts)

    def async_(self, **opts: Any) -> AsyncCouryo:
        opts.setdefault("api_key", "ck_test_abc")
        return AsyncCouryo(http_client=httpx.AsyncClient(transport=self.transport), _sleep=self.sleeps.append, **opts)


def api_error(status: int, code: str, type_: str = "invalid_request", headers: Optional[Dict[str, str]] = None) -> tuple:
    body = {
        "error": {
            "type": type_,
            "code": code,
            "message": f"msg {code}",
            "param": "to",
            "doc_url": f"https://couryo.com/docs/errors#{code}",
            "request_id": "req_1",
        }
    }
    return (status, body, headers or {})


SEND = {"from": "Loja <oi@loja.com.br>", "to": "ana@gmail.com", "subject": "Oi", "text": "Olá"}
