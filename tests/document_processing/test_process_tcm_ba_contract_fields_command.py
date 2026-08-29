from __future__ import annotations

import unittest

from barreiras_docproc.commands.process_tcm_ba_contract_fields import (
    batch_exit_code,
    run_batch,
)
from barreiras_docproc.processing import PageInput, TextArtifact
from barreiras_docproc.tcm_ba_contract_field_repository import (
    TcmBaContractFieldPageSet,
)
from barreiras_docproc.tcm_ba_contract_fields import (
    TcmBaContractFieldPersistResult,
)


def page_set(marker: str) -> TcmBaContractFieldPageSet:
    return TcmBaContractFieldPageSet(
        artifact=TextArtifact(
            raw_artifact_id=f"00000000-0000-0000-0000-00000000090{marker}",
            sha256=marker * 64,
            object_key=f"tcm-ba/{marker}.pdf",
        ),
        pages=(
            PageInput(
                page_number=1,
                parser_version="fixture/1.0.0",
                extraction_method="embedded_text",
                text="CONTRATO Nº 1/2021\nOBJETO: serviço.",
                sha256="f" * 64,
            ),
        ),
    )


class Repository:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def pending_page_sets(self, _limit: int):
        return (page_set("1"), page_set("2"))

    def persist_failure(self, artifact, **_kwargs):
        self.failed.append(artifact.sha256)


class Service:
    def process(self, artifact, _pages, segments):
        self.segment_count = len(segments)
        if artifact.sha256.startswith("2"):
            raise RuntimeError("sensitive database detail")
        return TcmBaContractFieldPersistResult(True, 1, 2, 0)


class ProcessTcmBaContractFieldsCommandTests(unittest.TestCase):
    def test_batch_segments_pages_and_records_sanitized_failure(self) -> None:
        repository = Repository()
        service = Service()

        summary = run_batch(
            repository=repository,
            service=service,
            limit=5,
        )

        self.assertEqual(service.segment_count, 1)
        self.assertEqual(summary.pending_found, 2)
        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.candidates_inserted, 1)
        self.assertEqual(summary.fields_observed, 2)
        self.assertEqual(summary.empty_candidates, 0)
        self.assertEqual(repository.failed, ["2" * 64])
        self.assertEqual(batch_exit_code(summary), 1)


if __name__ == "__main__":
    unittest.main()
