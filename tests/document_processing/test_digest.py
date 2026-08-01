from __future__ import annotations

import json
import unittest

from barreiras_docproc.assist import ContractViolationError
from barreiras_docproc.digest import (
    CHUNK_CHARS,
    build_digest_messages,
    chunk_text,
    digest_payload,
    job_idempotency_key,
    parse_digest_items,
)

CHUNK = (
    "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026\n\n"
    "Art. 1º Exonerar a pedido, a servidora MARIA DAS DORES SILVA, do "
    "cargo em comissão de Assessora Técnica.\n\n"
    "AVISO DE LICITAÇÃO — Pregão Eletrônico nº 012/2026, objeto: aquisição "
    "de gêneros alimentícios para a merenda escolar."
)


def content(items: list[dict]) -> str:
    return json.dumps({"items": items})


class ChunkTests(unittest.TestCase):
    def test_short_text_is_single_chunk(self) -> None:
        self.assertEqual(chunk_text(CHUNK), [CHUNK])

    def test_long_text_splits_within_limit(self) -> None:
        long_text = "\n\n".join(f"Parágrafo {i}. " + "x" * 400 for i in range(80))
        chunks = chunk_text(long_text)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), CHUNK_CHARS)

    def test_oversized_paragraph_is_hard_split(self) -> None:
        chunks = chunk_text("y" * (CHUNK_CHARS * 2 + 10))
        self.assertEqual(len(chunks), 3)


class ParseDigestTests(unittest.TestCase):
    def test_anchored_items_are_accepted_and_typed(self) -> None:
        items, dropped = parse_digest_items(
            content(
                [
                    {
                        "tipo": "exoneracao",
                        "titulo": "Exoneração de assessora",
                        "resumo": "A prefeitura desligou a servidora.",
                        "trecho": "Exonerar a pedido, a servidora MARIA",
                    },
                    {
                        "tipo": "tipo-desconhecido",
                        "titulo": "Licitação de merenda",
                        "resumo": "A prefeitura vai comprar alimentos.",
                        "trecho": "aquisição de gêneros alimentícios",
                    },
                ]
            ),
            CHUNK,
        )

        self.assertEqual(dropped, 0)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].item_type, "exoneracao")
        self.assertEqual(items[1].item_type, "outro")

    def test_item_without_literal_anchor_is_dropped(self) -> None:
        items, dropped = parse_digest_items(
            content(
                [
                    {
                        "tipo": "aviso",
                        "titulo": "Item inventado",
                        "resumo": "Não existe no texto.",
                        "trecho": "esta frase não está no diário oficial",
                    }
                ]
            ),
            CHUNK,
        )

        self.assertEqual(items, [])
        self.assertEqual(dropped, 1)

    def test_short_anchor_is_dropped(self) -> None:
        items, dropped = parse_digest_items(
            content(
                [
                    {
                        "tipo": "aviso",
                        "titulo": "Âncora curta",
                        "resumo": "Curta demais para identificar.",
                        "trecho": "PORTARIA",
                    }
                ]
            ),
            CHUNK,
        )

        self.assertEqual(items, [])
        self.assertEqual(dropped, 1)

    def test_missing_items_list_is_contract_violation(self) -> None:
        with self.assertRaises(ContractViolationError):
            parse_digest_items(json.dumps({"resumo": "sem lista"}), CHUNK)


class PayloadTests(unittest.TestCase):
    def test_prompt_demands_literal_quote_and_json(self) -> None:
        messages = build_digest_messages(CHUNK)
        self.assertIn("citação LITERAL", messages[1]["content"])
        self.assertIn("nunca invente", messages[0]["content"])

    def test_payload_carries_stats_and_partial_flag(self) -> None:
        items, _ = parse_digest_items(
            content(
                [
                    {
                        "tipo": "portaria",
                        "titulo": "Portaria 205",
                        "resumo": "Exoneração a pedido.",
                        "trecho": "PORTARIA Nº 205, DE 03 DE JUNHO DE 2026",
                    }
                ]
            ),
            CHUNK,
        )
        payload = digest_payload(
            edition=4687,
            year=2026,
            items=items,
            chunks_total=3,
            chunks_failed=1,
            items_dropped=2,
            partial=True,
            providers=["groq", "groq"],
        )

        self.assertEqual(payload["edition"], 4687)
        self.assertEqual(len(payload["items"]), 1)
        self.assertTrue(payload["stats"]["partial"])
        self.assertEqual(payload["stats"]["providers"], ["groq"])

    def test_job_key_changes_with_document_hash(self) -> None:
        self.assertNotEqual(
            job_idempotency_key("a" * 64),
            job_idempotency_key("b" * 64),
        )


if __name__ == "__main__":
    unittest.main()
