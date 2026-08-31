"""Benchmark privado e agregado da geometria de datas de empenho TCM-BA."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .pdf_layout import PdfLayoutPage
from .processing import TextArtifact
from .tcm_ba_commitment_layout import (
    diagnose_inline_explicit_issue_date,
    diagnose_spatial_issue_date,
)


@dataclass(frozen=True)
class TcmBaIssueDateLayoutTarget:
    artifact: TextArtifact
    candidate_page_counts: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class TcmBaIssueDateLayoutBenchmark:
    artifacts: int
    failed_artifacts: int
    missing_candidates: int
    failed_candidates: int
    multiple_candidate_page_candidates: int
    no_embedded_layout_candidates: int
    matched_candidates: int
    inline_labeled_date_candidates: int
    same_block_labeled_date_candidates: int
    no_date_candidates: int
    sole_unlabelled_date_candidates: int
    multiple_unlabelled_date_candidates: int
    multiple_label_candidates: int
    no_compatible_value_candidates: int
    ambiguous_value_candidates: int
    label_kind_counts: tuple[tuple[str, int], ...]
    date_format_counts: tuple[tuple[str, int], ...]
    date_role_counts: tuple[tuple[str, int], ...]
    direct_date_role_counts: tuple[tuple[str, int], ...]
    single_explicit_issue_date_candidates: int
    multiple_explicit_issue_date_candidates: int
    no_explicit_issue_date_candidates: int
    repeated_consensus_explicit_issue_date_candidates: int
    conflicting_explicit_issue_date_candidates: int
    safe_context_pattern_counts: tuple[tuple[str, int], ...]

    @property
    def accounted_candidates(self) -> int:
        return (
            self.failed_candidates
            + self.multiple_candidate_page_candidates
            + self.no_embedded_layout_candidates
            + self.matched_candidates
            + self.inline_labeled_date_candidates
            + self.same_block_labeled_date_candidates
            + self.no_date_candidates
            + self.sole_unlabelled_date_candidates
            + self.multiple_unlabelled_date_candidates
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


def benchmark_issue_date_layout(
    targets: tuple[TcmBaIssueDateLayoutTarget, ...],
    *,
    layout_loader: LayoutLoader,
) -> TcmBaIssueDateLayoutBenchmark:
    counters = {
        "failed_candidates": 0,
        "multiple_candidate_page_candidates": 0,
        "no_embedded_layout_candidates": 0,
        "matched_candidates": 0,
        "inline_labeled_date_candidates": 0,
        "same_block_labeled_date_candidates": 0,
        "no_date_candidates": 0,
        "sole_unlabelled_date_candidates": 0,
        "multiple_unlabelled_date_candidates": 0,
        "multiple_label_candidates": 0,
        "no_compatible_value_candidates": 0,
        "ambiguous_value_candidates": 0,
    }
    label_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    direct_role_counts: dict[str, int] = {}
    explicit_issue_candidate_counts = {"none": 0, "single": 0, "multiple": 0}
    explicit_consensus_counts = {"repeated_consensus": 0, "conflict": 0}
    context_counts: dict[str, int] = {}
    failed_artifacts = 0
    missing_candidates = 0
    for target in targets:
        page_counts = dict(target.candidate_page_counts)
        if len(page_counts) != len(target.candidate_page_counts) or any(
            page < 1 or count < 1 for page, count in page_counts.items()
        ):
            raise ValueError("O alvo de data possui contagem de página inválida.")
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
            diagnosis = diagnose_spatial_issue_date(layout.blocks)
            inline_consensus = diagnose_inline_explicit_issue_date(layout.blocks)
            if inline_consensus.status in explicit_consensus_counts:
                explicit_consensus_counts[inline_consensus.status] += 1
            for format_kind, count in diagnosis.date_format_counts:
                format_counts[format_kind] = format_counts.get(format_kind, 0) + count
            for role, count in diagnosis.date_role_counts:
                role_counts[role] = role_counts.get(role, 0) + count
            for role, count in diagnosis.direct_date_role_counts:
                direct_role_counts[role] = direct_role_counts.get(role, 0) + count
            if diagnosis.explicit_issue_date_count == 0:
                explicit_issue_candidate_counts["none"] += 1
            elif diagnosis.explicit_issue_date_count == 1:
                explicit_issue_candidate_counts["single"] += 1
            else:
                explicit_issue_candidate_counts["multiple"] += 1
            for pattern in diagnosis.safe_context_patterns:
                context_counts[pattern] = context_counts.get(pattern, 0) + 1
            if diagnosis.label_kind is not None:
                label_counts[diagnosis.label_kind] = (
                    label_counts.get(diagnosis.label_kind, 0) + 1
                )
            if diagnosis.status == "no_label":
                if diagnosis.date_value_count == 0:
                    counters["no_date_candidates"] += 1
                elif diagnosis.date_value_count == 1:
                    counters["sole_unlabelled_date_candidates"] += 1
                else:
                    counters["multiple_unlabelled_date_candidates"] += 1
                continue
            counter = {
                "matched": "matched_candidates",
                "inline_labeled": "inline_labeled_date_candidates",
                "same_block_labeled": "same_block_labeled_date_candidates",
                "multiple_labels": "multiple_label_candidates",
                "no_compatible_value": "no_compatible_value_candidates",
                "ambiguous_values": "ambiguous_value_candidates",
            }[diagnosis.status]
            counters[counter] += 1
    return TcmBaIssueDateLayoutBenchmark(
        artifacts=len(targets),
        failed_artifacts=failed_artifacts,
        missing_candidates=missing_candidates,
        label_kind_counts=tuple(sorted(label_counts.items())),
        date_format_counts=tuple(sorted(format_counts.items())),
        date_role_counts=tuple(sorted(role_counts.items())),
        direct_date_role_counts=tuple(sorted(direct_role_counts.items())),
        single_explicit_issue_date_candidates=explicit_issue_candidate_counts["single"],
        multiple_explicit_issue_date_candidates=explicit_issue_candidate_counts[
            "multiple"
        ],
        no_explicit_issue_date_candidates=explicit_issue_candidate_counts["none"],
        repeated_consensus_explicit_issue_date_candidates=(
            explicit_consensus_counts["repeated_consensus"]
        ),
        conflicting_explicit_issue_date_candidates=explicit_consensus_counts["conflict"],
        safe_context_pattern_counts=tuple(sorted(context_counts.items())),
        **counters,
    )


def benchmark_payload(
    benchmark: TcmBaIssueDateLayoutBenchmark,
) -> dict[str, object]:
    """Produz somente contagens, sem datas, identificadores ou trechos."""
    return {
        "artifacts": benchmark.artifacts,
        "failed_artifacts": benchmark.failed_artifacts,
        "missing_candidates": benchmark.missing_candidates,
        "accounted_candidates": benchmark.accounted_candidates,
        "matched_candidates": benchmark.matched_candidates,
        "diagnostic_candidates": {
            "inline_labeled_date": benchmark.inline_labeled_date_candidates,
            "same_block_labeled_date": benchmark.same_block_labeled_date_candidates,
        },
        "excluded_candidates": {
            "failed_artifact": benchmark.failed_candidates,
            "multiple_candidates_on_page": benchmark.multiple_candidate_page_candidates,
            "no_embedded_layout": benchmark.no_embedded_layout_candidates,
            "no_date": benchmark.no_date_candidates,
            "sole_unlabelled_date": benchmark.sole_unlabelled_date_candidates,
            "multiple_unlabelled_dates": benchmark.multiple_unlabelled_date_candidates,
            "multiple_labels": benchmark.multiple_label_candidates,
            "no_compatible_value": benchmark.no_compatible_value_candidates,
            "ambiguous_values": benchmark.ambiguous_value_candidates,
        },
        "label_kind_counts": dict(benchmark.label_kind_counts),
        "date_format_counts": dict(benchmark.date_format_counts),
        "date_role_counts": dict(benchmark.date_role_counts),
        "direct_date_role_counts": dict(benchmark.direct_date_role_counts),
        "explicit_issue_date_candidates": {
            "single": benchmark.single_explicit_issue_date_candidates,
            "multiple": benchmark.multiple_explicit_issue_date_candidates,
            "none": benchmark.no_explicit_issue_date_candidates,
        },
        "explicit_issue_date_consensus": {
            "repeated_consensus": (
                benchmark.repeated_consensus_explicit_issue_date_candidates
            ),
            "conflict": benchmark.conflicting_explicit_issue_date_candidates,
        },
        "safe_context_pattern_counts": dict(benchmark.safe_context_pattern_counts),
        "gate": "PASS" if benchmark.complete else "BLOCK",
    }