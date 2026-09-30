from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from barreiras_collectors.commands.collect_receita_cnpj import (
    build_extract,
    records_for,
)
from barreiras_collectors.connectors.receita_cnpj import (
    ReceitaCnpjError,
    RemoteFile,
    build_registry,
    download,
    parse_propfind,
    read_naturezas,
    scan_empresas,
    scan_estabelecimentos,
)

PROPFIND = (
    b'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
    b"<d:response><d:href>/public.php/webdav/2026-09/</d:href>"
    b"<d:propstat><d:prop>"
    b"<d:getlastmodified>Mon, 14 Sep 2026 15:08:06 GMT</d:getlastmodified>"
    b"</d:prop></d:propstat></d:response>"
    b"<d:response><d:href>/public.php/webdav/2026-09/Empresas1.zip</d:href>"
    b"<d:propstat><d:prop><d:getcontentlength>77900000</d:getcontentlength>"
    b"<d:getlastmodified>Mon, 14 Sep 2026 14:59:35 GMT</d:getlastmodified>"
    b"</d:prop></d:propstat></d:response></d:multistatus>"
)


def official_zip(directory: Path, name: str, lines: list[str]) -> Path:
    path = directory / name
    body = "\n".join(lines).encode("latin-1")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("K3241.K03200Y1.D60912.CSV", body)
    return path


def estabelecimento(basico, ordem, dv, fantasia, telefone="77999998888"):
    fields = [
        basico,
        ordem,
        dv,
        "1",
        fantasia,
        "02",
        "20100101",
        "00",
        "",
        "",
        "20100101",
        "4711302",
        "",
        "RUA",
        "SEM NOME",
        "10",
        "",
        "CENTRO",
        "47800000",
        "BA",
        "3845",
        "77",
        telefone,
        "",
        "",
        "",
        "",
        "mail@x.com",
        "",
        "",
    ]
    return ";".join(f'"{value}"' for value in fields)


class ParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())

    def test_propfind_lists_files_with_size(self) -> None:
        items = parse_propfind(PROPFIND)
        self.assertEqual(items[1][0].rsplit("/", 1)[-1], "Empresas1.zip")
        self.assertEqual(items[1][1], 77900000)
        self.assertIsNone(items[0][1])

    def test_scans_only_targets_and_drops_contact_data(self) -> None:
        empresas = official_zip(
            self.directory,
            "Empresas1.zip",
            [
                '"44493204";"GSV MAIS ALIMENTOS LTDA";"2062";"49";"10000,00";"01";""',
                '"99999999";"OUTRA EMPRESA LTDA";"2062";"49";"1,00";"01";""',
            ],
        )
        estabs = official_zip(
            self.directory,
            "Estabelecimentos1.zip",
            [
                estabelecimento(
                    "44493204", "0001", "87", "COMERCIAL E PAPELARIA VALOIS"
                ),
                estabelecimento("44493204", "0002", "68", "FILIAL QUE NAO FOI PEDIDA"),
            ],
        )
        naturezas = official_zip(
            self.directory,
            "Naturezas.zip",
            [
                '"2062";"Sociedade Empresária Limitada"',
                '"2135";"Empresário (Individual)"',
            ],
        )
        targets = frozenset({"44493204000187", "11111111000111"})
        found_empresas = scan_empresas(empresas, frozenset(c[:8] for c in targets))
        found_estabs = scan_estabelecimentos(estabs, targets)
        registry, missing = build_registry(
            targets, found_empresas, found_estabs, read_naturezas(naturezas)
        )
        self.assertEqual(missing, ["11111111000111"])
        [row] = registry
        self.assertEqual(row["razao_social"], "GSV MAIS ALIMENTOS LTDA")
        self.assertEqual(row["nome_fantasia"], "COMERCIAL E PAPELARIA VALOIS")
        self.assertEqual(
            row["natureza_juridica_descricao"], "Sociedade Empresária Limitada"
        )
        self.assertNotIn("telefone", str(row))
        self.assertNotIn("mail@x.com", str(row))
        self.assertNotIn("SEM NOME", str(row))

    def test_extract_carries_source_hashes_and_one_record_per_cnpj(self) -> None:
        extract = build_extract(
            month="2026-09",
            targets=frozenset({"44493204000187"}),
            files={
                "Empresas1.zip": {
                    "url": "https://arquivos.receitafederal.gov.br/x",
                    "size": 1,
                    "last_modified": "t",
                    "sha256": "a" * 64,
                }
            },
            registry=[
                {"cnpj": "44493204000187", "razao_social": "GSV MAIS ALIMENTOS LTDA"}
            ],
            missing=[],
            requested_at="2026-09-30T00:00:00+00:00",
            received_at="2026-09-30T01:00:00+00:00",
        )
        self.assertEqual(extract.cursor["source_files"], {"Empresas1.zip": "a" * 64})
        self.assertEqual(
            extract.body_sha256, hashlib.sha256(extract.raw_body).hexdigest()
        )
        [record] = records_for(extract)
        self.assertEqual(record.record_type, "receita_cnpj_registry")
        self.assertEqual(record.payload["registry_month"], "2026-09")
        self.assertEqual(
            record.source_record_key, "receita:cnpj:44493204000187:2026-09"
        )


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, *, url: str, status: int = 200) -> None:
        super().__init__(body)
        self.status = status
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class DownloadTests(unittest.TestCase):
    def remote(self, size: int) -> RemoteFile:
        return RemoteFile(
            month="2026-09", name="Naturezas.zip", size=size, last_modified="t"
        )

    def test_hashes_while_downloading_and_checks_size(self) -> None:
        body = b"zip-bytes"
        with tempfile.TemporaryDirectory() as directory:
            result = download(
                self.remote(len(body)),
                Path(directory),
                opener=lambda request, timeout: FakeResponse(
                    body, url=request.full_url
                ),
            )
            self.assertEqual(result.sha256, hashlib.sha256(body).hexdigest())
            with self.assertRaisesRegex(ReceitaCnpjError, "esperado"):
                download(
                    self.remote(len(body) + 1),
                    Path(directory),
                    opener=lambda request, timeout: FakeResponse(
                        body, url=request.full_url
                    ),
                )

    def test_refuses_redirect_out_of_receita(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ReceitaCnpjError, "host oficial"),
        ):
            download(
                self.remote(3),
                Path(directory),
                opener=lambda request, timeout: FakeResponse(
                    b"abc", url="https://mirror.example/x"
                ),
            )


if __name__ == "__main__":
    unittest.main()
