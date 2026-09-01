import assert from "node:assert/strict";
import test from "node:test";

import {
  buildObligationCoverageMatrix,
  obligationCoverageStatusLabel,
  parseObligationCoverageApiPayload,
} from "../../apps/web/lib/obligation-coverage-matrix.mjs";

function row(periodStart, coverageStatus, overrides = {}) {
  const fiscalYear = Number(periodStart.slice(0, 4));
  return {
    coverageId: `coverage-${periodStart}`,
    fiscalYear,
    periodStart,
    periodEnd: `${periodStart.slice(0, 8)}28`,
    coverageStatus,
    sourceUrl: "https://barreiras.ba.gov.br/balancete.pdf",
    documentArtifactSha256: "a".repeat(64),
    searchEvidenceSha256: null,
    evidenceArtifactCount: null,
    conflictPreviousPeriodAmount: null,
    conflictReportedPriorAmount: null,
    conflictDifferenceAmount: null,
    checkedAt: "2026-08-31T12:00:00Z",
    methodologyVersion: "public-obligation-coverage/1.2.0",
    ...overrides,
  };
}

test("organiza restos a pagar por ano e mês sem preencher lacunas como zero", () => {
  const matrix = buildObligationCoverageMatrix([
    row("2026-03-01", "published"),
    row("2026-02-01", "section_absent"),
    row("2025-12-01", "document_not_found", {
      documentArtifactSha256: null,
      searchEvidenceSha256: "b".repeat(64),
      evidenceArtifactCount: 1,
    }),
  ]);

  assert.equal(matrix.latestPeriod, "2026-03");
  assert.deepEqual(matrix.years.map((year) => year.year), [2026, 2025, 2024, 2023, 2022, 2021]);
  assert.equal(matrix.years[0].months[1].status, "section_absent");
  assert.equal(matrix.years[0].months[2].status, "published");
  assert.equal(matrix.years[0].months[3].status, "not_due");
  assert.equal(matrix.years[1].months[0].status, "unclassified");
  assert.equal(matrix.years[1].months[11].status, "document_not_found");
});

test("valida o payload em tempo real e rejeita competência duplicada", () => {
  const validRow = row("2026-03-01", "published");
  assert.deepEqual(
    parseObligationCoverageApiPayload({ state: "available", rows: [validRow] }),
    { state: "available", rows: [validRow] },
  );
  assert.equal(
    parseObligationCoverageApiPayload({ state: "available", rows: [validRow, validRow] }),
    null,
  );
  assert.deepEqual(parseObligationCoverageApiPayload({ state: "unavailable" }), {
    state: "unavailable",
  });
});

test("explica cada estado sem depender apenas da cor", () => {
  assert.deepEqual(
    [
      "published",
      "section_absent",
      "section_incomplete",
      "source_conflict",
      "document_not_found",
      "document_not_confirmed",
      "unclassified",
      "not_due",
    ].map(obligationCoverageStatusLabel),
    [
      "Valor publicado",
      "Seção ausente",
      "Seção incompleta",
      "Divergência oficial",
      "Documento não localizado",
      "Documento não confirmado",
      "Não classificado",
      "Fora do período acompanhado",
    ],
  );
});
