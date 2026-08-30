"""Benchmark privado e agregado da geometria de credores TCM-BA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .pdf_layout import PdfLayoutPage
from .processing import TextArtifact
from .tcm_ba_commitment_layout import diagnose_spatial_creditor


@dataclass(frozen=True)
class TcmBaCreditorLayoutTarget:
    artifact: TextArtifact
    candidate_page_counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class TcmBaCreditorLayoutBenchmark:
    artifacts: int
    failed_artifacts: int
    missing_candidates: int
    failed_candidates: int
    multiple_candidate_page_candidates: int
    no_embedded_layout_candidates: int
    matched_candidates: int
    no_label_candidates: int
    multiple_label_candidates: int
    no_compatible_value_candidates: int
    ambiguous_value_candidates: int
    label_kind_counts: tuple[tuple[str, int], ...]

    @property
    def accounted_candidates(self) -> int:
        return (
            self.failed_candidates
            + self.multiple_candidate_page_candidates
            + self.no_embedded_layout_candidates
            + self.matched_candidates
            + self.no_label_candidates
            + self.multiple_label_candidates
            + self.no_compatible_value_candidates
            + self.ambiguous_value_candidates
        )

    @property
    def complete(self) -> bool:
        return (
            self.failed_artifacts == 0
            and self.failed_candidates == 0
            and self.accounted_candidates == self.missing_candidates
        )


LayoutLoader = Callable[[TextArtifact], tuple[PdfLayoutPage, ...]]


def benchmark_creditor_layout(
    targets: tuple[TcmBaCreditorLayoutTarget, ...],
    *,
    layout_loader: LayoutLoader,
) -> TcmBaCreditorLayoutBenchmark:
    counters = {
        "failed_candidates": 0,
        "multiple_candidate_page_candidates": 0,
        "no_embedded_layout_candidates": 0,
        "matched_candidates": 0,
        "no_label_candidates": 0,
        "multiple_label_candidates": 0,
        "no_compatible_value_candidates": 0,
        "ambiguous_value_candidates": 0,
    }
    label_counts: dict[str, int] = {}
    failed_artifacts = 0
    missing_candidates = 0
    for target in targets:
        page_counts = dict(target.candidate_page_counts)
        if len(page_counts) != len(target.candidate_page_counts) or any(
            page < 1 or count < 1 for page, count in page_counts.items()
        ):
            raise ValueError("O alvo de credor possui contagem de página inválida.")
        target_candidates = sum(page_counts.values())
        missing_candidates += target_candidates
        try:
            layouts = {
                layout.page_number: layout for layout in layout_loader(target.artifact)
            }
        except Exception:
            failed_artifacts += 1
            counters["failed_candidates"] += target_candidates
            continue
        for page_number, candidate_count in page_counts.items():
            if candidate_count != 1:
                counters["multiple_candidate_page_candidates"] += candidate_count
                continue
            layout = layouts.get(page_number)
            if layout is None or layout.extraction_method != "embedded_layout":
                counters["no_embedded_layout_candidates"] += 1
                continue
            diagnosis = diagnose_spatial_creditor(layout.blocks)
            if diagnosis.label_kind is not None:
                label_counts[diagnosis.label_kind] = (
                    label_counts.get(diagnosis.label_kind, 0) + 1
                )
            counter = {
                "matched": "matched_candidates",
                "no_label": "no_label_candidates",
                "multiple_labels": "multiple_label_candidates",
                "no_compatible_value": "no_compatible_value_candidates",
                "ambiguous_values": "ambiguous_value_candidates",
            }[diagnosis.status]
            counters[counter] += 1
    return TcmBaCreditorLayoutBenchmark(
        artifacts=len(targets),
        failed_artifacts=failed_artifacts,
        missing_candidates=missing_candidates,
        label_kind_counts=tuple(sorted(label_counts.items())),
        **counters,
    )


def benchmark_payload(
    benchmark: TcmBaCreditorLayoutBenchmark,
) -> dict[str, object]:
    """Produz somente contagens, sem identificadores, nomes ou trechos."""
    return {
        "artifacts": benchmark.artifacts,
        "failed_artifacts": benchmark.failed_artifacts,
        "missing_candidates": benchmark.missing_candidates,
        "accounted_candidates": benchmark.accounted_candidates,
        "matched_candidates": benchmark.matched_candidates,
        "excluded_candidates": {
            "failed_artifact": benchmark.failed_candidates,
            "multiple_candidates_on_page": benchmark.multiple_candidate_page_candidates,
            "no_embedded_layout": benchmark.no_embedded_layout_candidates,
            "no_label": benchmark.no_label_candidates,
            "multiple_labels": benchmark.multiple_label_candidates,
            "no_compatible_value": benchmark.no_compatible_value_candidates,
            "ambiguous_values": benchmark.ambiguous_value_candidates,
        },
        "label_kind_counts": dict(benchmark.label_kind_counts),
        "gate": "PASS" if benchmark.complete else "BLOCK",
    }
