import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPayrollCoverageMatrix,
  parsePayrollCoverageApiPayload,
  payrollCoverageStatusLabel,
} from "../../apps/web/lib/payroll-coverage-matrix.mjs";

function row(referenceMonth, coverageStatus, overrides = {}) {
  return {
    referenceMonth,
    coverageStatus,
    coverageNote: "Situação confirmada no catálogo oficial.",
    catalogDocumentCount: coverageStatus === "document_not_found" ? 0 : 1,
    preservedDocumentCount: coverageStatus === "published" ? 1 : 0,
    sourceUrl: "https://barreiras.ba.gov.br/folha/",
    artifactSha256: coverageStatus === "published" ? "a".repeat(64) : null,
    catalogCheckedAt: "2026-08-31T12:00:00Z",
    methodologyVersion: "payroll-coverage/1.0.0",
    ...overrides,
  };
}

test("organiza a folha por competência sem transformar ausência em zero", () => {
  const matrix = buildPayrollCoverageMatrix([
    row("2026-03-01", "published"),
    row("2026-02-01", "processing_pending"),
    row("2025-12-01", "document_not_found"),
  ]);

  assert.equal(matrix.latestPeriod, "2026-03");
  assert.equal(matrix.years.length, 6);
  assert.equal(matrix.years[0].months[1].status, "processing_pending");
  assert.equal(matrix.years[0].months[2].status, "published");
  assert.equal(matrix.years[0].months[3].status, "not_due");
  assert.equal(matrix.years[1].months[0].status, "unclassified");
  assert.equal(matrix.years[1].months[11].status, "document_not_found");
});

test("valida o payload em tempo real e rejeita competência duplicada", () => {
  const validRow = row("2026-03-01", "published");
  assert.deepEqual(parsePayrollCoverageApiPayload({ state: "available", rows: [validRow] }), {
    state: "available",
    rows: [validRow],
  });
  assert.equal(
    parsePayrollCoverageApiPayload({ state: "available", rows: [validRow, validRow] }),
    null,
  );
  assert.deepEqual(parsePayrollCoverageApiPayload({ state: "unavailable" }), {
    state: "unavailable",
  });
});

test("explica os estados da folha por texto", () => {
  assert.deepEqual(
    ["published", "processing_pending", "source_conflict", "document_not_found", "unclassified", "not_due"].map(payrollCoverageStatusLabel),
    ["Publicado", "Em validação", "Conflito de ciclos", "Documento não localizado", "Não classificado", "Fora do período acompanhado"],
  );
});
