"""Aplica a regra do ADR 0086 aos empenhos preservados ainda sem decisão.

Lê os contratos municipais preservados, decide cada empenho pendente pela
versão atual da regra e grava as decisões append-only. Não publica nada.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence

from ..commitment_contract_links import (
    RULE_VERSION,
    candidate_contracts,
    index_contracts,
    link_commitment,
)
from ..commitment_link_repository import CommitmentLinkRepository

BATCH_SIZE = 5000


def link_pending(
    repository: CommitmentLinkRepository, *, max_commitments: int
) -> dict[str, object]:
    contracts = index_contracts(repository.municipal_contracts())
    outcomes: Counter[str] = Counter()
    inserted = 0
    decided = 0
    while decided < max_commitments:
        pending = repository.pending_commitments(
            RULE_VERSION, min(BATCH_SIZE, max_commitments - decided)
        )
        if not pending:
            break
        decisions = tuple(
            (item.raw_record_id, link_commitment(item.row, contracts))
            for item in pending
        )
        inserted += repository.record_decisions(decisions)
        decided += len(decisions)
        outcomes.update(
            f"{decision.state}:{decision.reason}" if decision.reason else decision.state
            for _, decision in decisions
        )
    # A revisão humana precisa ver os contratos que o número citado aponta;
    # a mesma regra que decidiu calcula os candidatos, sem reimplementá-la em SQL.
    candidates = tuple(
        (link_id, contract)
        for link_id, pending in repository.links_without_candidates(RULE_VERSION)
        for contract in candidate_contracts(pending.row, contracts)
    )
    return {
        "rule_version": RULE_VERSION,
        "indexed_contract_keys": len(contracts),
        "decided": decided,
        "inserted": inserted,
        "outcomes": dict(sorted(outcomes.items())),
        "review_candidates_inserted": repository.record_candidates(candidates),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-commitments", type=int, default=50000)
    args = parser.parse_args(argv)
    if args.max_commitments < 1:
        raise SystemExit("--max-commitments deve ser positivo.")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL é obrigatório.")
    summary = link_pending(
        CommitmentLinkRepository.from_dsn(database_url),
        max_commitments=args.max_commitments,
    )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
