"""Transporte HTTP restrito para fontes cadastradas."""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


class HttpTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse: ...


def validate_https_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Somente URLs HTTPS são permitidas.")
    if parsed.username or parsed.password:
        raise ValueError("Credenciais não são permitidas na URL.")
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if hostname not in allowed_hosts:
        raise ValueError(f"Host não permitido: {hostname or '<vazio>'}.")
    if parsed.port not in (None, 443):
        raise ValueError("Porta não permitida para a fonte.")


class _RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_repeats = 2
    max_redirections = 5

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = urljoin(req.full_url, newurl)
        validate_https_url(target, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, target)


class UrllibTransport:
    """Transporte stdlib com redirects limitados ao host oficial."""

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self.allowed_hosts = allowed_hosts
        self._opener = urllib.request.build_opener(
            _RestrictedRedirectHandler(allowed_hosts)
        )

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_seconds: float,
        max_body_bytes: int,
    ) -> HttpResponse:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes deve ser pelo menos 1.")
        validate_https_url(url, self.allowed_hosts)
        request = urllib.request.Request(  # noqa: S310 - allowlist HTTPS estrita.
            url,
            headers=dict(headers),
            method="GET",
        )
        try:
            with self._opener.open(
                request,
                timeout=timeout_seconds,
            ) as response:
                body = response.read(max_body_bytes + 1)
                if len(body) > max_body_bytes:
                    raise ResponseTooLargeError(
                        f"Resposta excede o limite de {max_body_bytes} bytes."
                    )
                final_url = response.geturl()
                validate_https_url(final_url, self.allowed_hosts)
                return HttpResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=body,
                    final_url=final_url,
                )
        except urllib.error.HTTPError as error:
            final_url = error.geturl()
            validate_https_url(final_url, self.allowed_hosts)
            body = error.read(max_body_bytes + 1)
            if len(body) > max_body_bytes:
                raise ResponseTooLargeError(
                    f"Resposta de erro excede {max_body_bytes} bytes."
                ) from error
            return HttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                body=body,
                final_url=final_url,
            )


class ResponseTooLargeError(RuntimeError):
    """A resposta ultrapassou o limite configurado antes de ser preservada."""
