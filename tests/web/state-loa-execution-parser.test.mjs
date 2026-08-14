import assert from "node:assert/strict";
import test from "node:test";

const parserModule = await import(
  "../../apps/web/lib/state-loa-execution.mjs"
).catch(() => ({
  parseStateLoaExecutionRows: () => null,
  parseStateLoaExecutionSummary: () => null,
}));

const {
  parseStateLoaExecutionRows,
  parseStateLoaExecutionSummary,
} = parserModule;

const confirmedRow = {
  fiscal_year: 2026,
  amendment_number: "3024",
  author_external_code: "500069",
  author_key: "antonio-henrique-junior",
  author_name: "Antonio Henrique Júnior",
  authorized_amount: "195010.00",
  official_description: "Apoio a Barreiras",
  page_number: 12,
  loa_evidence_text: "Trecho literal da LOA",
  loa_source_url: "https://www.ba.gov.br/seplan/loa.pdf",
  loa_source_artifact_sha256: "a".repeat(64),
  loa_evidence_sha256: "b".repeat(64),
  execution_status: "execution_confirmed",
  loa_scope_occurrences: 1,
  execution_occurrences: 1,
  committed_amount: "173453.00",
  liquidated_amount: "173453.00",
  paid_amount: "0.00",
  execution_source_url: "https://dados.ba.gov.br/emendas.zip",
  execution_source_artifact_sha256: "c".repeat(64),
  execution_evidence_sha256: "d".repeat(64),
  execution_source_collected_at: "2026-08-14T09:10:00+00:00",
  methodology_version: "bahia-state-loa-public-execution/1.0.0",
};

test("valida correspondência única e preserva zero oficial como valor", () => {
  const rows = parseStateLoaExecutionRows([confirmedRow]);
  assert.equal(rows?.[0]?.executionStatus, "execution_confirmed");
  assert.equal(rows?.[0]?.paidAmount, "0.00");
  assert.equal(rows?.[0]?.executionEvidenceSha256, "d".repeat(64));
});

test("rejeita registro bloqueado que tente vazar valor ou evidência de execução", () => {
  assert.equal(parseStateLoaExecutionRows([{
    ...confirmedRow,
    execution_status: "ambiguous_official_key",
    loa_scope_occurrences: 2,
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: "0.00",
    execution_source_url: null,
    execution_source_artifact_sha256: null,
    execution_evidence_sha256: null,
    execution_source_collected_at: null,
  }]), null);
});

test("aceita bloqueio auditável quando todos os campos de execução estão ausentes", () => {
  const rows = parseStateLoaExecutionRows([{
    ...confirmedRow,
    execution_status: "not_found_in_execution_source",
    execution_occurrences: 0,
    committed_amount: null,
    liquidated_amount: null,
    paid_amount: null,
    execution_source_url: null,
    execution_source_artifact_sha256: null,
    execution_evidence_sha256: null,
    execution_source_collected_at: null,
  }]);
  assert.equal(rows?.[0]?.executionStatus, "not_found_in_execution_source");
  assert.equal(rows?.[0]?.paidAmount, null);
});

test("valida o resumo SQL sem recalcular valores no frontend", () => {
  assert.deepEqual(parseStateLoaExecutionSummary([{
    fiscal_year: 2026,
    total_amendment_count: 27,
    matched_amendment_count: 9,
    ambiguous_amendment_count: 17,
    not_found_amendment_count: 1,
    unavailable_scope_count: 0,
    authorized_total: "9017541.00",
    matched_authorized_total: "7349341.00",
    committed_total: "349933.00",
    liquidated_total: "329933.00",
    paid_total: "329933.00",
    methodology_version: "bahia-state-loa-public-execution-summary/1.0.0",
  }]), {
    fiscalYear: 2026,
    totalAmendmentCount: 27,
    matchedAmendmentCount: 9,
    ambiguousAmendmentCount: 17,
    notFoundAmendmentCount: 1,
    unavailableScopeCount: 0,
    authorizedTotal: "9017541.00",
    matchedAuthorizedTotal: "7349341.00",
    committedTotal: "349933.00",
    liquidatedTotal: "329933.00",
    paidTotal: "329933.00",
    methodologyVersion: "bahia-state-loa-public-execution-summary/1.0.0",
  });
});
