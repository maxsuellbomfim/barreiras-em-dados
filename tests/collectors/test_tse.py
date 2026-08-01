from __future__ import annotations

import io
import unittest
import zipfile

from barreiras_collectors.connectors.tse import (
    BARREIRAS_TSE_CODE,
    TseError,
    aggregate_by_candidate,
    extract_state_csv,
    package_url,
    rows_for_barreiras,
)

HEADER = (
    "ANO_ELEICAO;NR_TURNO;CD_MUNICIPIO;NM_MUNICIPIO;NR_ZONA;DS_CARGO;"
    "SQ_CANDIDATO;NR_CANDIDATO;NM_CANDIDATO;NM_URNA_CANDIDATO;SG_PARTIDO;"
    "QT_VOTOS_NOMINAIS;DS_SIT_TOT_TURNO"
)


def linha(
    municipio: str,
    codigo: str,
    zona: str,
    sequencial: str,
    votos: str,
    nome: str = "FULANO DE TAL",
) -> str:
    return (
        f"2024;1;{codigo};{municipio};{zona};Vereador;{sequencial};12345;"
        f"{nome};FULANO;PXY;{votos};ELEITO"
    )


def csv_bytes(*linhas: str) -> bytes:
    return "\n".join((HEADER, *linhas)).encode("latin-1")


def zip_with(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


class PackageTests(unittest.TestCase):
    def test_url_carries_year(self) -> None:
        self.assertIn("2022", package_url(2022))

    def test_extracts_only_bahia_file(self) -> None:
        package = zip_with(
            "votacao_candidato_munzona_2024_BA.csv",
            csv_bytes(linha("BARREIRAS", BARREIRAS_TSE_CODE, "1", "9", "10")),
        )

        self.assertIn(b"BARREIRAS", extract_state_csv(package, 2024))

    def test_missing_state_file_is_explicit(self) -> None:
        package = zip_with("votacao_candidato_munzona_2024_SP.csv", b"x")

        with self.assertRaises(TseError):
            extract_state_csv(package, 2024)

    def test_corrupt_package_is_explicit(self) -> None:
        with self.assertRaises(TseError):
            extract_state_csv(b"nao-e-zip", 2024)


class RowsTests(unittest.TestCase):
    def test_keeps_only_barreiras_by_official_code(self) -> None:
        content = csv_bytes(
            linha("BARREIRAS", BARREIRAS_TSE_CODE, "1", "9", "10"),
            linha("SALVADOR", "38490", "2", "8", "99"),
            # Nome parecido, código diferente: não é Barreiras.
            linha("BARREIRAS DO NORTE", "99999", "3", "7", "50"),
        )

        rows, total = rows_for_barreiras(content)

        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SQ_CANDIDATO"], "9")

    def test_missing_column_is_explicit_failure(self) -> None:
        quebrado = b"ANO_ELEICAO;CD_MUNICIPIO\n2024;33634"

        with self.assertRaises(TseError):
            rows_for_barreiras(quebrado)

    def test_no_barreiras_rows_is_explicit_failure(self) -> None:
        content = csv_bytes(linha("SALVADOR", "38490", "1", "9", "10"))

        with self.assertRaises(TseError):
            rows_for_barreiras(content)


class AggregationTests(unittest.TestCase):
    def test_sums_zones_by_candidate_not_by_name(self) -> None:
        content = csv_bytes(
            linha("BARREIRAS", BARREIRAS_TSE_CODE, "1", "9", "100"),
            linha("BARREIRAS", BARREIRAS_TSE_CODE, "2", "9", "250"),
            # Mesmo nome, sequencial diferente: pessoa distinta.
            linha("BARREIRAS", BARREIRAS_TSE_CODE, "1", "77", "40"),
        )
        rows, _ = rows_for_barreiras(content)

        aggregated = aggregate_by_candidate(rows)

        self.assertEqual(len(aggregated), 2)
        self.assertEqual(aggregated[0]["votos_em_barreiras"], 350)
        self.assertEqual(aggregated[0]["zonas"], 2)
        self.assertEqual(aggregated[1]["votos_em_barreiras"], 40)

    def test_non_numeric_votes_is_explicit_failure(self) -> None:
        content = csv_bytes(
            linha("BARREIRAS", BARREIRAS_TSE_CODE, "1", "9", "muitos")
        )
        rows, _ = rows_for_barreiras(content)

        with self.assertRaises(TseError):
            aggregate_by_candidate(rows)


if __name__ == "__main__":
    unittest.main()
