from __future__ import annotations

import unittest

from barreiras_reconciliation import commitment_contract_links as links
from barreiras_reconciliation.commitment_contract_links import (
    ContractKey,
    MunicipalContract,
    contract_citations,
    contract_number_key,
    index_contracts,
    link_commitment,
    party_name_key,
)

CONTRACTS = index_contracts(
    (
        MunicipalContract(
            "contrato:1", "070-FMS/2025", "Construtora e Serviços Chagas LTDA"
        ),
        MunicipalContract("contrato:2", "070/2025", "OUTRA EMPRESA LTDA"),
        MunicipalContract(
            "contrato:3", "260/2021", "COMAFLEX COMERCIO DE MANGUEIRAS E FLEXIVEIS LTDA"
        ),
        MunicipalContract(
            "contrato:4",
            "260/2021 - 1º ADITIVO",
            "COMAFLEX COMERCIO DE MANGUEIRAS E FLEXIVEIS LTDA",
        ),
        MunicipalContract("contrato:5", "004-FMS/2023", "CLEVERSON ALVES MACÊDO"),
        MunicipalContract("contrato:6", "004-FMS/2023", "CLEVERSON ALVES MACEDO"),
        MunicipalContract("contrato:7", "134/2026", "SMAT CARTUCHOS E LOCAÇÃO LTDA"),
    )
)


def commitment(key: str, history: str, creditor: str = "") -> dict[str, str]:
    return {
        links.FIELD_KEY: key,
        links.FIELD_HISTORY: history,
        links.FIELD_CREDITOR: creditor,
    }


class ContractNumberKeyTests(unittest.TestCase):
    def test_keeps_organ_suffix_letter_and_year(self) -> None:
        self.assertEqual(
            contract_number_key("070-FMS/2025"), ContractKey(70, "", "FMS", 2025)
        )
        self.assertEqual(
            contract_number_key("116/2023FMS"), ContractKey(116, "", "FMS", 2023)
        )
        self.assertEqual(
            contract_number_key("216/2023 FMS"), ContractKey(216, "", "FMS", 2023)
        )
        self.assertEqual(
            contract_number_key("003-C/2018"), ContractKey(3, "C", "", 2018)
        )
        self.assertEqual(
            contract_number_key("0074/2026"), ContractKey(74, "", "", 2026)
        )
        self.assertNotEqual(
            contract_number_key("070/2025"), contract_number_key("070-FMS/2025")
        )

    def test_malformed_numbers_have_no_key(self) -> None:
        for text in ("082-FMS/202", "109/203", "071/20224", "1ºTERMO-ADT.", "TESTEFMS"):
            self.assertIsNone(contract_number_key(text), text)


class CitationTests(unittest.TestCase):
    def test_recognizes_the_observed_citation_forms(self) -> None:
        cases = {
            "Contrato nº 070-FMS/2025 no valor de": ContractKey(70, "", "FMS", 2025),
            "contrato de nº 260/2021 no valor": ContractKey(260, "", "", 2021),
            "CONTRATO N°133/2026 com vigência até 18/06/2027": ContractKey(
                133, "", "", 2026
            ),
            "contrato 071-FMS/2025, no valor": ContractKey(71, "", "FMS", 2025),
            "Contrato n.º 116/2023FMS": ContractKey(116, "", "FMS", 2023),
        }
        for history, key in cases.items():
            self.assertEqual(
                [found for _, found in contract_citations(history)], [key], history
            )

    def test_ignores_texts_that_do_not_cite_a_contract_number(self) -> None:
        for history in (
            "Contratação de empresa especializada",
            "CONTRATO (C.C. 123456), deste município",
            "Contrato de Financiamento nº 0123456789",
            "CONTRATO - Referente proventos de agosto",
        ):
            self.assertEqual(contract_citations(history), (), history)


class PartyNameTests(unittest.TestCase):
    def test_ignores_accents_legal_form_and_prepositions(self) -> None:
        self.assertEqual(
            party_name_key("CONSTRUTORA E SERVIÇOS CHAGAS EIRELI"),
            party_name_key("Construtora e Serviços Chagas LTDA"),
        )
        self.assertEqual(
            party_name_key("COMAFLEX COMÉRCIO DE MANGUEIRAS FLEXÍVEIS LTDA"),
            party_name_key("COMAFLEX COMERCIO DE MANGUEIRAS E FLEXIVEIS LTDA"),
        )

    def test_does_not_absorb_typos(self) -> None:
        self.assertNotEqual(
            party_name_key("SMART CARTUCHOS E LOCAÇÕES LTDA"),
            party_name_key("SMAT CARTUCHOS E LOCAÇÃO LTDA"),
        )


class CandidateContractTests(unittest.TestCase):
    def test_returns_the_contracts_the_cited_number_points_to(self) -> None:
        duplicated = links.candidate_contracts(
            commitment("O-3", "Contrato nº 004-FMS/2023", "CLEVERSON ALVES MACEDO"),
            CONTRACTS,
        )
        divergent = links.candidate_contracts(
            commitment("O-2", "Contrato de nº 134/2026", "SMART LTDA"), CONTRACTS
        )

        self.assertEqual(
            sorted(contract.record_key for contract in duplicated),
            ["contrato:5", "contrato:6"],
        )
        self.assertEqual(
            [contract.record_key for contract in divergent], ["contrato:7"]
        )

    def test_ambiguous_or_illegible_citations_have_no_candidates(self) -> None:
        for history in (
            "contrato nº 070/2025 e contrato nº 260/2021",
            "Contrato nº 082-FMS/202",
            "sem citação",
        ):
            self.assertEqual(
                links.candidate_contracts(commitment("O-1", history), CONTRACTS), ()
            )


class LinkDecisionTests(unittest.TestCase):
    def test_links_only_with_single_contract_and_same_contractor(self) -> None:
        decision = link_commitment(
            commitment(
                "O-252163",
                "Concorrência Pública nº 001/2025, Contrato nº 070-FMS/2025 no valor",
                "CONSTRUTORA E SERVIÇOS CHAGAS EIRELI",
            ),
            CONTRACTS,
        )
        self.assertEqual(decision.state, links.LINKED)
        self.assertEqual(decision.contract_record_key, "contrato:1")
        self.assertIn("070-FMS/2025", decision.cited_excerpt)
        self.assertEqual(decision.rule_version, "commitment-contract-link/1.0.0")

    def test_amendment_rows_are_not_separate_contracts(self) -> None:
        decision = link_commitment(
            commitment(
                "O-1",
                "Contrato nº 260/2021",
                "COMAFLEX COMÉRCIO DE MANGUEIRAS FLEXÍVEIS LTDA",
            ),
            CONTRACTS,
        )
        self.assertEqual(
            (decision.state, decision.contract_record_key), (links.LINKED, "contrato:3")
        )

    def test_unconfirmed_cases_keep_reason_and_never_point_to_a_contract(self) -> None:
        cases = {
            "favorecido_divergente": commitment(
                "O-2", "Contrato de nº 134/2026", "SMART CARTUCHOS E LOCAÇÕES LTDA"
            ),
            "varios_contratos": commitment(
                "O-3", "Contrato nº 004-FMS/2023", "CLEVERSON ALVES MACEDO"
            ),
            "nenhum_contrato": commitment("O-4", "Contrato nº 999/2025", "X LTDA"),
            "numero_ilegivel": commitment("O-5", "Contrato nº 082-FMS/202", "X LTDA"),
            "multiplas_citacoes": commitment(
                "O-6", "contrato nº 070/2025 e contrato nº 260/2021", "X LTDA"
            ),
        }
        for reason, row in cases.items():
            decision = link_commitment(row, CONTRACTS)
            self.assertEqual(
                (decision.state, decision.reason), (links.UNCONFIRMED, reason), reason
            )
            self.assertIsNone(decision.contract_record_key)

    def test_extra_budget_and_uncited_commitments_are_not_linked(self) -> None:
        extra = link_commitment(
            commitment(
                "E-57409", "Contrato nº 070-FMS/2025", "CONSTRUTORA E SERVIÇOS CHAGAS"
            ),
            CONTRACTS,
        )
        uncited = link_commitment(commitment("O-7", "Tarifas bancárias"), CONTRACTS)

        self.assertEqual(extra.state, links.OUT_OF_SCOPE)
        self.assertEqual(uncited.state, links.NO_CITATION)
        self.assertIsNone(extra.contract_record_key)
        self.assertIsNone(uncited.contract_record_key)


if __name__ == "__main__":
    unittest.main()
