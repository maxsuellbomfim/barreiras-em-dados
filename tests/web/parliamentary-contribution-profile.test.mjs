import assert from "node:assert/strict";
import test from "node:test";

import {
  parseParliamentaryContributionProfileRows,
} from "../../apps/web/lib/parliamentary-contribution-profile.mjs";

const federalRow = {
  sphere: "federal",
  legislature_number: 57,
  legislature_label: "57ª Legislatura da Câmara dos Deputados",
  begins_on: "2023-02-01",
  ends_on: "2027-01-31",
  full_fiscal_year_from: 2024,
  full_fiscal_year_to: 2026,
  official_source_url:
    "https://www2.camara.leg.br/atividade-legislativa/comissoes/grupos-de-trabalho/57a-legislatura/",
  official_source_note: "Legislatura federal corrente, iniciada em 2023.",
  excluded_transition_years: [2023],
  ranking_amount_stage: "destination",
  author_key: "deputada exemplo",
  author_name: "DEPUTADA EXEMPLO",
  representative_source_kind: "federal",
  representative_external_id: "123",
  representative_profile_url: "https://www.camara.leg.br/deputados/123",
  association_status: "approved_official_crosswalk",
  total_amendment_count: 2,
  total_ranking_amount: "1500000.00",
  total_committed_amount: "1000000.00",
  total_liquidated_amount: null,
  total_paid_amount: "750000.00",
  row_position: 1,
  contribution_key: "official:10:20249001",
  fiscal_year: 2025,
  amendment_number: "20249001",
  beneficiary_name: "MUNICÍPIO DE BARREIRAS",
  object_description: "Construção de unidade de saúde",
  ranking_amount: "1000000.00",
  committed_amount: "800000.00",
  liquidated_amount: null,
  paid_amount: "500000.00",
  execution_status: "matched_exact",
  primary_source_url: "https://transferegov.br/emenda-20249001.zip",
  primary_artifact_sha256: "a".repeat(64),
  secondary_source_url: "https://transferegov.br/historico-20249001.zip",
  secondary_artifact_sha256: "b".repeat(64),
  evidence_excerpt: null,
  page_number: null,
  methodology_version: "parliamentary-legislature-contributions/1.0.0",
};

test("organizes one public profile without merging financial stages", () => {
  const parsed = parseParliamentaryContributionProfileRows([
    federalRow,
    {
      ...federalRow,
      row_position: 2,
      contribution_key: "historical:11:20249002",
      amendment_number: "20249002",
      ranking_amount: "500000.00",
      committed_amount: "200000.00",
      paid_amount: "250000.00",
      execution_status: "historical_only",
      secondary_source_url: null,
      secondary_artifact_sha256: null,
    },
  ]);

  assert.ok(parsed);
  assert.equal(parsed.authorName, "DEPUTADA EXEMPLO");
  assert.equal(parsed.totalAmendmentCount, 2);
  assert.equal(parsed.totalRankingAmount, "1500000.00");
  assert.equal(parsed.totalCommittedAmount, "1000000.00");
  assert.equal(parsed.totalLiquidatedAmount, null);
  assert.equal(parsed.totalPaidAmount, "750000.00");
  assert.deepEqual(parsed.contributions.map((row) => row.amendmentNumber), [
    "20249001",
    "20249002",
  ]);
});

test("rejects a response that mixes authors, legislatures or unsafe evidence", () => {
  assert.equal(parseParliamentaryContributionProfileRows([
    federalRow,
    { ...federalRow, row_position: 2, author_key: "outra pessoa" },
  ]), null);
  assert.equal(parseParliamentaryContributionProfileRows([
    { ...federalRow, fiscal_year: 2023 },
  ]), null);
  assert.equal(parseParliamentaryContributionProfileRows([
    { ...federalRow, primary_source_url: "http://fonte-insegura.example" },
  ]), null);
  assert.equal(parseParliamentaryContributionProfileRows([
    { ...federalRow, primary_artifact_sha256: "invalido" },
  ]), null);
});

test("accepts state evidence and explicit absence of execution as unknown, not zero", () => {
  const stateRow = {
    ...federalRow,
    sphere: "state",
    legislature_number: 20,
    legislature_label: "20ª Legislatura da Assembleia Legislativa da Bahia",
    official_source_url: "https://www.al.ba.gov.br/midia-center/noticias/55953",
    ranking_amount_stage: "authorized",
    author_key: "deputado estadual",
    author_name: "Deputado Estadual",
    representative_source_kind: null,
    representative_external_id: null,
    representative_profile_url: null,
    association_status: "not_linked",
    total_amendment_count: 1,
    total_ranking_amount: "250000.00",
    total_committed_amount: null,
    total_liquidated_amount: null,
    total_paid_amount: null,
    contribution_key: "state:2025:101:" + "c".repeat(64),
    fiscal_year: 2025,
    amendment_number: "101",
    beneficiary_name: null,
    ranking_amount: "250000.00",
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    execution_status: "not_found_in_execution_source",
    primary_source_url: "https://www.ba.gov.br/seplan/loa-2025.pdf",
    primary_artifact_sha256: "c".repeat(64),
    secondary_source_url: null,
    secondary_artifact_sha256: null,
    evidence_excerpt: "BARREIRAS DEPUTADO ESTADUAL 250000",
    page_number: 12,
  };
  const parsed = parseParliamentaryContributionProfileRows([stateRow]);
  assert.ok(parsed);
  assert.equal(parsed.contributions[0].paidAmount, null);
  assert.equal(
    parsed.contributions[0].executionStatus,
    "not_found_in_execution_source",
  );
  assert.equal(parsed.contributions[0].evidenceExcerpt, stateRow.evidence_excerpt);
});

test("returns no profile for an empty RPC response", () => {
  assert.equal(parseParliamentaryContributionProfileRows([]), null);
});
