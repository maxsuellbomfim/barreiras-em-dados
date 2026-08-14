import assert from "node:assert/strict";
import test from "node:test";

import {
  groupParliamentaryLegislatureRankings,
  parseParliamentaryLegislatureRankingRows,
} from "../../apps/web/lib/parliamentary-legislature-rankings.mjs";

const baseRow = {
  sphere: "federal",
  legislature_number: 57,
  legislature_label: "57ª Legislatura da Câmara dos Deputados",
  begins_on: "2023-02-01",
  ends_on: "2027-01-31",
  full_fiscal_year_from: 2024,
  full_fiscal_year_to: 2026,
  official_source_url:
    "https://www2.camara.leg.br/atividade-legislativa/comissoes/grupos-de-trabalho/57a-legislatura/",
  official_source_note: "Legislatura federal iniciada em 2023 e encerrada em 2027.",
  excluded_transition_years: [2023],
  ranking_amount_stage: "destination",
  rank_position: 1,
  author_key: "deputada exemplo",
  author_name: "DEPUTADA EXEMPLO",
  representative_source_kind: "federal",
  representative_external_id: "123",
  representative_profile_url: "https://www.camara.leg.br/deputados/123",
  association_status: "approved_official_crosswalk",
  amendment_count: 3,
  ranking_amount: "1500000.00",
  committed_amount: "1000000.00",
  liquidated_amount: null,
  paid_amount: "750000.00",
  first_year: 2024,
  last_year: 2026,
  methodology_version: "parliamentary-legislature-transfer-ranking/1.0.0",
};

test("parses strict legislature ranking rows and keeps financial stages separate", () => {
  assert.deepEqual(parseParliamentaryLegislatureRankingRows([baseRow]), [{
    sphere: "federal",
    legislatureNumber: 57,
    legislatureLabel: "57ª Legislatura da Câmara dos Deputados",
    beginsOn: "2023-02-01",
    endsOn: "2027-01-31",
    fullFiscalYearFrom: 2024,
    fullFiscalYearTo: 2026,
    officialSourceUrl: baseRow.official_source_url,
    officialSourceNote: baseRow.official_source_note,
    excludedTransitionYears: [2023],
    rankingAmountStage: "destination",
    rankPosition: 1,
    authorKey: "deputada exemplo",
    authorName: "DEPUTADA EXEMPLO",
    representativeSourceKind: "federal",
    representativeExternalId: "123",
    representativeProfileUrl: "https://www.camara.leg.br/deputados/123",
    associationStatus: "approved_official_crosswalk",
    amendmentCount: 3,
    rankingAmount: "1500000.00",
    committedAmount: "1000000.00",
    liquidatedAmount: null,
    paidAmount: "750000.00",
    firstYear: 2024,
    lastYear: 2026,
    methodologyVersion: "parliamentary-legislature-transfer-ranking/1.0.0",
  }]);
});

test("rejects mixed spheres, invalid legislature boundaries and incompatible profile links", () => {
  assert.equal(parseParliamentaryLegislatureRankingRows([
    { ...baseRow, sphere: "state", ranking_amount_stage: "destination" },
  ]), null);
  assert.equal(parseParliamentaryLegislatureRankingRows([
    { ...baseRow, full_fiscal_year_from: 2023 },
  ]), null);
  assert.equal(parseParliamentaryLegislatureRankingRows([
    {
      ...baseRow,
      representative_source_kind: "state",
      representative_profile_url: "https://www.camara.leg.br/deputados/123",
    },
  ]), null);
});

test("accepts an empty legislature marker and groups terms without inventing ten names", () => {
  const stateMarker = {
    ...baseRow,
    sphere: "state",
    legislature_number: 19,
    legislature_label: "19ª Legislatura da Assembleia Legislativa da Bahia",
    begins_on: "2019-02-01",
    ends_on: "2023-01-31",
    full_fiscal_year_from: 2020,
    full_fiscal_year_to: 2022,
    official_source_url: "https://www.al.ba.gov.br/midia-center/noticias/32631",
    official_source_note: "Legislatura estadual iniciada em fevereiro de 2019.",
    ranking_amount_stage: "authorized",
    rank_position: null,
    author_key: null,
    author_name: null,
    representative_source_kind: null,
    representative_external_id: null,
    representative_profile_url: null,
    association_status: null,
    amendment_count: null,
    ranking_amount: null,
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    first_year: null,
    last_year: null,
  };
  const parsed = parseParliamentaryLegislatureRankingRows([baseRow, stateMarker]);
  assert.ok(parsed);
  const groups = groupParliamentaryLegislatureRankings(parsed);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].rankings.length, 0);
  assert.equal(groups[1].rankings.length, 1);
});
