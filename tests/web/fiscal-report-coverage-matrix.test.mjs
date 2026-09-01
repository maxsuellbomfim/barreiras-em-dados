import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFiscalReportCoverageMatrix,
  parseFiscalReportCoverageApiPayload,
} from "../../apps/web/lib/fiscal-report-coverage-matrix.mjs";

function entry(overrides = {}) {
  return {
    resource: "rreo",
    fiscalYear: 2025,
    referenceMonth: 2,
    documentUrl: "https://barreiras.ba.gov.br/rreo-2025-02.pdf",
    documentPreserved: true,
    artifactSha256: "a".repeat(64),
    collectedAt: "2026-08-30T12:00:00.000Z",
    ...overrides,
  };
}

test("separa os seis bimestres do RREO dos três quadrimestres do RGF", () => {
  const matrix = buildFiscalReportCoverageMatrix([
    entry(),
    entry({ resource: "rgf", referenceMonth: 4, documentUrl: "https://barreiras.ba.gov.br/rgf-2025-04.pdf" }),
  ], { today: "2025-06-01", startYear: 2025 });

  assert.ok(matrix);
  assert.deepEqual(matrix.columns.map(({ resource, referenceMonth }) => [resource, referenceMonth]), [
    ["rreo", 2], ["rreo", 4], ["rreo", 6], ["rreo", 8], ["rreo", 10], ["rreo", 12],
    ["rgf", 4], ["rgf", 8], ["rgf", 12],
  ]);
  assert.deepEqual(matrix.years[0].periods.map(({ status }) => status), [
    "preserved", "not_found", "not_due", "not_due", "not_due", "not_due",
    "preserved", "not_due", "not_due",
  ]);
});

test("distingue documento catalogado de PDF preservado e prefere a evidência preservada", () => {
  const matrix = buildFiscalReportCoverageMatrix([
    entry({ documentPreserved: false, artifactSha256: null, collectedAt: "2026-08-31T10:00:00.000Z" }),
    entry({ documentUrl: "https://barreiras.ba.gov.br/rreo-2025-02-preservado.pdf" }),
    entry({ referenceMonth: 4, documentPreserved: false, artifactSha256: null }),
  ], { today: "2026-09-01", startYear: 2025 });

  assert.ok(matrix);
  assert.equal(matrix.years[1].periods[0].status, "preserved");
  assert.equal(matrix.years[1].periods[0].entry.documentUrl, "https://barreiras.ba.gov.br/rreo-2025-02-preservado.pdf");
  assert.equal(matrix.years[1].periods[0].evidenceCount, 2);
  assert.equal(matrix.years[1].periods[1].status, "catalogued");
});

test("falha fechado diante de mês incompatível, URL insegura ou contrato extra", () => {
  assert.equal(buildFiscalReportCoverageMatrix([entry({ referenceMonth: 3 })]), null);
  assert.equal(buildFiscalReportCoverageMatrix([entry({ documentUrl: "http://inseguro.test/rreo.pdf" })]), null);
  assert.equal(parseFiscalReportCoverageApiPayload({ state: "available", entries: [{ ...entry(), extra: true }] }), null);
});

test("payload vazio confirmado gera calendário sem transformar períodos futuros em falta", () => {
  const parsed = parseFiscalReportCoverageApiPayload({ state: "available", entries: [] });
  assert.deepEqual(parsed, { state: "available", entries: [] });
  const matrix = buildFiscalReportCoverageMatrix(parsed.entries, { today: "2026-09-01", startYear: 2026 });
  assert.ok(matrix);
  assert.deepEqual(matrix.years[0].periods.map(({ status }) => status), [
    "not_found", "not_found", "not_found", "not_due", "not_due", "not_due",
    "not_found", "not_due", "not_due",
  ]);
});
