import assert from "node:assert/strict";
import test from "node:test";

const parserModule = await import(
  "../../apps/web/lib/state-loa-execution-groups.mjs"
).catch(() => ({ parseStateLoaExecutionGroups: () => null }));

const { parseStateLoaExecutionGroups } = parserModule;

const validRow = {
  fiscal_year: 2026,
  author_external_code: "500069",
  author_key: "antonio-henrique-junior",
  author_name: "Antonio Henrique Júnior",
  agency_code: "SEC",
  budget_unit_code: "APG",
  action_code: "3334",
  amendment_count: 2,
  amendment_numbers: ["3052", "3053"],
  authorized_total: "237000.00",
  initial_budget_amount: "237000.00",
  current_budget_amount: "237000.00",
  committed_amount: "0.00",
  liquidated_amount: "0.00",
  paid_amount: "0.00",
  execution_code: "2026.500069.SEC.APG.3334",
  execution_source_url: "https://dados.ba.gov.br/emendas.zip",
  execution_source_artifact_sha256: "a".repeat(64),
  execution_evidence_sha256: "b".repeat(64),
  execution_source_collected_at: "2026-08-14T09:10:00+00:00",
  methodology_version: "bahia-state-loa-execution-group/1.0.0",
};

test("aceita execução agregada sem repartir valores entre as emendas", () => {
  assert.deepEqual(parseStateLoaExecutionGroups([validRow]), [{
    fiscalYear: 2026,
    authorExternalCode: "500069",
    authorKey: "antonio-henrique-junior",
    authorName: "Antonio Henrique Júnior",
    agencyCode: "SEC",
    budgetUnitCode: "APG",
    actionCode: "3334",
    amendmentCount: 2,
    amendmentNumbers: ["3052", "3053"],
    authorizedTotal: "237000.00",
    initialBudgetAmount: "237000.00",
    currentBudgetAmount: "237000.00",
    committedAmount: "0.00",
    liquidatedAmount: "0.00",
    paidAmount: "0.00",
    executionCode: "2026.500069.SEC.APG.3334",
    executionSourceUrl: "https://dados.ba.gov.br/emendas.zip",
    executionSourceArtifactSha256: "a".repeat(64),
    executionEvidenceSha256: "b".repeat(64),
    executionSourceCollectedAt: "2026-08-14T09:10:00+00:00",
    methodologyVersion: "bahia-state-loa-execution-group/1.0.0",
  }]);
});

test("rejeita grupo que não tenha ao menos duas emendas distintas", () => {
  assert.equal(parseStateLoaExecutionGroups([{
    ...validRow,
    amendment_count: 2,
    amendment_numbers: ["3052", "3052"],
  }]), null);
});

test("rejeita fonte ou integridade inválida", () => {
  assert.equal(parseStateLoaExecutionGroups([{
    ...validRow,
    execution_source_url: "http://dados.ba.gov.br/emendas.zip",
  }]), null);
  assert.equal(parseStateLoaExecutionGroups([{
    ...validRow,
    execution_source_artifact_sha256: "curto",
  }]), null);
});
