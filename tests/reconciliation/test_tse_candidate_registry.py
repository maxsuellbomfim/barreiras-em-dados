from __future__ import annotations

import csv
import io
import unittest
import zipfile

from barreiras_reconciliation.tse_candidate_registry import (
    CandidateRegistryError,
    candidates_from_registry,
    extract_bahia_registry,
)

CPF_FIXTURE = "529982247" + "25"


def registry_zip(rows: list[dict[str, str]], *, year: int = 2024) -> bytes:
    columns = (
        "ANO_ELEICAO",
        "SG_UF",
        "DS_CARGO",
        "SQ_CANDIDATO",
        "NR_CPF_CANDIDATO",
        "NM_CANDIDATO",
        "NM_URNA_CANDIDATO",
    )
    text = io.StringIO()
    writer = csv.DictWriter(
        text,
        fieldnames=columns,
        delimiter=";",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            f"consulta_cand_{year}_BA.csv",
            text.getvalue().encode("latin-1"),
        )
    return package.getvalue()


class TseCandidateRegistryTest(unittest.TestCase):
    def test_filters_approved_ids_and_keeps_cpf_private(self) -> None:
        package = registry_zip(
            [
                {
                    "ANO_ELEICAO": "2024",
                    "SG_UF": "BA",
                    "DS_CARGO": "VEREADOR",
                    "SQ_CANDIDATO": "123",
                    "NR_CPF_CANDIDATO": CPF_FIXTURE,
                    "NM_CANDIDATO": "PESSOA TESTE",
                    "NM_URNA_CANDIDATO": "PESSOA",
                },
                {
                    "ANO_ELEICAO": "2024",
                    "SG_UF": "BA",
                    "DS_CARGO": "VEREADOR",
                    "SQ_CANDIDATO": "999",
                    "NR_CPF_CANDIDATO": "1" * 11,
                    "NM_CANDIDATO": "FORA DO RECORTE",
                    "NM_URNA_CANDIDATO": "FORA",
                },
            ]
        )

        state_csv = extract_bahia_registry(package, 2024)
        identities = candidates_from_registry(
            state_csv,
            year=2024,
            approved_candidate_ids={"123"},
        )

        self.assertEqual(len(identities), 1)
        self.assertEqual(identities[0].candidate_id, "123")
        self.assertEqual(identities[0].cpf, CPF_FIXTURE)
        self.assertEqual(
            identities[0].public_payload,
            {
                "ano": "2024",
                "cargo": "VEREADOR",
                "nome": "PESSOA TESTE",
                "nome_urna": "PESSOA",
                "sq_candidato": "123",
                "uf": "BA",
            },
        )
        self.assertNotIn("cpf", str(identities[0].public_payload).lower())
        self.assertIn(CPF_FIXTURE.encode("ascii"), identities[0].private_source_payload)

    def test_keeps_an_approved_candidate_with_invalid_cpf_as_unavailable(
        self,
    ) -> None:
        package = registry_zip(
            [
                {
                    "ANO_ELEICAO": "2024",
                    "SG_UF": "BA",
                    "DS_CARGO": "VEREADOR",
                    "SQ_CANDIDATO": "123",
                    "NR_CPF_CANDIDATO": "1" * 11,
                    "NM_CANDIDATO": "PESSOA TESTE",
                    "NM_URNA_CANDIDATO": "PESSOA",
                }
            ]
        )

        identities = candidates_from_registry(
            extract_bahia_registry(package, 2024),
            year=2024,
            approved_candidate_ids={"123"},
        )

        self.assertEqual(len(identities), 1)
        self.assertIsNone(identities[0].cpf)
        self.assertEqual(
            identities[0].identifier_issue,
            "invalid_official_value",
        )
        self.assertNotIn("cpf", str(identities[0].public_payload).lower())

    def test_rejects_a_layout_without_the_official_cpf_column(self) -> None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "consulta_cand_2024_BA.csv",
                b"ANO_ELEICAO;SQ_CANDIDATO\n2024;123\n",
            )

        with self.assertRaisesRegex(CandidateRegistryError, "layout do TSE mudou"):
            candidates_from_registry(
                extract_bahia_registry(package.getvalue(), 2024),
                year=2024,
                approved_candidate_ids={"123"},
            )


if __name__ == "__main__":
    unittest.main()
