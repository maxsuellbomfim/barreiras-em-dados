import assert from "node:assert/strict";
import test from "node:test";

import {
  parseParliamentaryLegislatureCoverageRows,
} from "../../apps/web/lib/parliamentary-legislature-coverage.mjs";

const federalCoverage = {
  sphere: "federal",
  legislature_number: 57,
  legislature_label: "57ª Legislatura da Câmara dos Deputados",
  begins_on: "2023-02-01",
  ends_on: "2027-01-31",
  full_fiscal_year_from: 2024,
  full_fiscal_year_to: 2026,
  official_source_url: "https://www.camara.leg.br/deputados/",
  official_source_note: "Período oficial da Câmara.",
  excluded_transition_years: [2023],
  ranking_amount_stage: "destination",
  contribution_count: 10,
  author_count: 4,
  linked_author_count: 3,
  unlinked_author_count: 1,
  with_object_count: 9,
  object_field_status: "published_by_source",
  with_beneficiary_count: 8,
  beneficiary_field_status: "published_by_source",
  with_committed_count: 6,
  with_liquidated_count: null,
  liquidated_field_status: "not_published_in_source",
  with_paid_count: 5,
  execution_confirmed_count: 7,
  execution_unresolved_count: 3,
  primary_evidence_count: 10,
  methodology_version: "parliamentary-legislature-coverage/1.0.0",
};

test("parses coverage without turning unavailable source fields into zero", () => {
  const parsed = parseParliamentaryLegislatureCoverageRows([federalCoverage]);
  assert.ok(parsed);
  assert.equal(parsed[0].withLiquidatedCount, null);
  assert.equal(parsed[0].liquidatedFieldStatus, "not_published_in_source");
  assert.equal(parsed[0].withBeneficiaryCount, 8);
});

test("accepts the state source limit for beneficiary and keeps execution counts", () => {
  const parsed = parseParliamentaryLegislatureCoverageRows([{
    ...federalCoverage,
    sphere: "state",
    legislature_number: 20,
    legislature_label: "20ª Legislatura da Assembleia Legislativa da Bahia",
    official_source_url: "https://www.al.ba.gov.br/midia-center/noticias/55953",
    ranking_amount_stage: "authorized",
    with_beneficiary_count: null,
    beneficiary_field_status: "not_published_in_source",
    with_liquidated_count: 4,
    liquidated_field_status: "published_by_source",
  }]);
  assert.ok(parsed);
  assert.equal(parsed[0].withBeneficiaryCount, null);
  assert.equal(parsed[0].withLiquidatedCount, 4);
});

test("rejects incoherent totals and fabricated zero for an unavailable field", () => {
  assert.equal(parseParliamentaryLegislatureCoverageRows([{
    ...federalCoverage,
    linked_author_count: 4,
    unlinked_author_count: 1,
  }]), null);
  assert.equal(parseParliamentaryLegislatureCoverageRows([{
    ...federalCoverage,
    with_liquidated_count: 0,
  }]), null);
  assert.equal(parseParliamentaryLegislatureCoverageRows([{
    ...federalCoverage,
    primary_evidence_count: 11,
  }]), null);
});
