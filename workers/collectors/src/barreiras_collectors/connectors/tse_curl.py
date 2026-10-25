"""Download local limitado usando o curl já fornecido pelo Windows.

O download Python do pacote nacional demora além do timeout nesta máquina.
Não segue redirecionamentos, não lê configuração pessoal e não recebe segredos.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..http import HttpResponse, validate_https_url
from .tse import ALLOWED_HOSTS


class TseCurlTransport:
    def get(self, url, *, headers, timeout_seconds, max_body_bytes) -> HttpResponse:
        validate_https_url(url, ALLOWED_HOSTS)
        executable = shutil.which("curl.exe") or shutil.which("curl")
        if executable is None:
            raise OSError("curl não foi encontrado para o download do TSE.")
        with tempfile.TemporaryDirectory(prefix="barreiras-tse-") as directory:
            target = Path(directory) / "package.zip"
            args = [
                executable,
                "--disable",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--max-time",
                str(timeout_seconds),
                "--max-filesize",
                str(max_body_bytes),
                "--output",
                str(target),
                "--write-out",
                "%{http_code}",
            ]
            for key, value in headers.items():
                args.extend(["--header", f"{key}: {value}"])
            args.append(url)
            try:
                result = subprocess.run(  # noqa: S603 - HTTPS allowlist; no shell.
                    args,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds + 10,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError(
                    "Download do TSE excedeu o tempo permitido."
                ) from error
            if result.returncode != 0:
                raise OSError(
                    f"Download do TSE interrompido (curl {result.returncode})."
                )
            if not result.stdout.strip().isdigit():
                raise OSError("Download do TSE não retornou status HTTP válido.")
            if target.stat().st_size > max_body_bytes:
                raise OSError("Download do TSE excedeu o limite de tamanho.")
            return HttpResponse(
                int(result.stdout.strip()), {}, target.read_bytes(), url
            )
