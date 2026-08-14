import assert from "node:assert/strict";
import test from "node:test";

const filterModule = await import(
  "../../apps/web/lib/parliamentary-transfer-year-filter.mjs"
).catch(() => ({
  resolveCurrentFederalTransferYear: () => null,
  buildCurrentTransferRankingRequest: () => ({}),
  buildCurrentTransfersRequest: () => ({}),
}));

const resolveCurrentFederalTransferYear =
  filterModule.resolveCurrentFederalTransferYear ?? (() => null);
const buildCurrentTransferRankingRequest =
  filterModule.buildCurrentTransferRankingRequest ?? (() => ({}));
const buildCurrentTransfersRequest =
  filterModule.buildCurrentTransfersRequest ?? (() => ({}));

const coverage = [
  { fiscalYear: 2026, coverageStatus: "empty", publishedAmendmentCount: 0 },
  { fiscalYear: 2025, coverageStatus: "complete", publishedAmendmentCount: 3 },
  { fiscalYear: 2024, coverageStatus: "failed", publishedAmendmentCount: null },
  { fiscalYear: 2023, coverageStatus: "complete", publishedAmendmentCount: 2 },
];

test("sem ano solicitado escolhe o ano mais recente com emendas publicadas", () => {
  assert.equal(resolveCurrentFederalTransferYear(undefined, coverage), 2025);
});

test("permite consultar um ano coberto mesmo quando a API atual ficou vazia", () => {
  assert.equal(resolveCurrentFederalTransferYear("2026", coverage), 2026);
});

test("ano inválido ou fora da cobertura volta ao ano mais recente com emendas", () => {
  assert.equal(resolveCurrentFederalTransferYear("2022", coverage), 2025);
  assert.equal(resolveCurrentFederalTransferYear("2025abc", coverage), 2025);
  assert.equal(resolveCurrentFederalTransferYear(["2023", "2025"], coverage), 2025);
});

test("sem cobertura classificada não inventa um ano", () => {
  assert.equal(resolveCurrentFederalTransferYear("2025", null), null);
  assert.equal(resolveCurrentFederalTransferYear(undefined, []), null);
});

test("pedido do ranking envia o ano selecionado e mantém autoria separada", () => {
  assert.deepEqual(buildCurrentTransferRankingRequest("person", 2025), {
    author_scope: "person",
    fiscal_year_filter: 2025,
    page_size: 50,
  });
  assert.deepEqual(buildCurrentTransferRankingRequest("collective", 2026), {
    author_scope: "collective",
    fiscal_year_filter: 2026,
    page_size: 50,
  });
});

test("pedido das emendas limita a paginação ao ano selecionado no servidor", () => {
  assert.deepEqual(buildCurrentTransfersRequest(2025), {
    fiscal_year_filter: 2025,
    author_kind_filter: null,
    page_size: 200,
  });
});
