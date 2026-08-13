"""Download limitado do cadastro oficial de candidaturas do TSE."""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .tse_candidate_registry import source_url

OFFICIAL_HOST = "cdn.tse.jus.br"
DEFAULT_MAX_BYTES = 700 * 1024 * 1024


class CandidateRegistryDownloadError(RuntimeError):
    """O download não satisfez o contrato de origem e tamanho."""


def fetch_candidate_registry(
    year: int,
    *,
    opener: Callable[..., object] = urlopen,
    max_bytes: int = DEFAULT_MAX_BYTES,
    sleep: Callable[[float], None] = time.sleep,
    attempts: int = 3,
) -> bytes:
    if max_bytes < 1 or attempts < 1:
        raise ValueError("Limites do download são inválidos.")
    url = source_url(year)
    # A URL é construída internamente e validada novamente após redirects.
    request = Request(  # noqa: S310
        url,
        headers={"User-Agent": "Barreiras360/identity-registry"},
    )
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            with opener(request, timeout=60.0) as response:
                final_url = str(response.geturl())
                parsed = urlparse(final_url)
                if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST:
                    raise CandidateRegistryDownloadError(
                        "O cadastro foi redirecionado para fora do host oficial."
                    )
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise CandidateRegistryDownloadError(
                        "O cadastro oficial excedeu o limite de download."
                    )
                return payload
        except CandidateRegistryDownloadError:
            raise
        except HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise CandidateRegistryDownloadError(
                    "O TSE recusou o download do cadastro oficial."
                ) from error
            last_error = error
        except (URLError, TimeoutError, OSError) as error:
            if attempt == attempts:
                raise CandidateRegistryDownloadError(
                    "O cadastro oficial do TSE não pôde ser baixado."
                ) from error
            last_error = error
        sleep(float(2 ** (attempt - 1)))
    raise CandidateRegistryDownloadError(
        "O cadastro oficial do TSE não pôde ser baixado."
    ) from last_error
