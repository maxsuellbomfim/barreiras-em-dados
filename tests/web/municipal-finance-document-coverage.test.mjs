import assert from "node:assert/strict";
import test from "node:test";

import {
  buildMunicipalFinanceDocumentCoverage,
  municipalFinanceDocumentCoverageStatusLabel,
  parseMunicipalFinanceDocumentCoverageApiPayload,
  toMunicipalFinanceDocumentCoverageEntry,
} from "../../apps/web/lib/municipal-finance-document-coverage.mjs";

function entry(overrides = {}) {
  return {
    documentId: "00000000-0000-4000-8000-000000000001",
    resource: "balancetes",
    fiscalYear: 2025,
    referenceMonth: 1,
    documentUrl: "https://barreiras.mtransparente.com.br/balancete-2025-01.pdf",
    documentPreserved: true,
    artifactSha256: "a".repeat(64),
    collectedAt: "2026-08-30T12:00:00.000Z",
    ...overrides,
  };
}

test("separa balancete, receita e despesa sem somar nem ocultar versões", () => {
  const matrix = buildMunicipalFinanceDocumentCoverage([
    entry(),
    entry({
      documentId: "00000000-0000-4000-8000-000000000002",
      documentUrl: "https://barreiras.mtransparente.com.br/balancete-retificado.pdf",
      collectedAt: "2026-08-31T12:00:00.000Z",
    }),
    entry({
      documentId: "00000000-0000-4000-8000-000000000003",
      resource: "pdc-resumo-execucao-da-receita",
      documentUrl: "https://barreiras.mtransparente.com.br/receita-2025-01.pdf",
    }),
    entry({
      documentId: "00000000-0000-4000-8000-000000000004",
      resource: "pdc-resumo-execucao-da-despesa",
      documentUrl: "https://barreiras.mtransparente.com.br/despesa-2025-01.pdf",
      documentPreserved: false,
      artifactSha256: null,
    }),
  ], { today: "2025-03-02", startYear: 2025 });

  assert.ok(matrix);
  const january = matrix.years[0].months[0];
  assert.deepEqual(january.families.map(({ status }) => status), [
    "preserved", "preserved", "catalogued",
  ]);
  assert.equal(january.families[0].evidenceCount, 2);
  assert.equal(
    january.families[0].entry.documentUrl,
    "https://barreiras.mtransparente.com.br/balancete-retificado.pdf",
  );
});

test("distingue prazo aberto de competência não localizada no catálogo consultado", () => {
  const matrix = buildMunicipalFinanceDocumentCoverage([], {
    today: "2026-09-01",
    startYear: 2026,
  });

  assert.ok(matrix);
  assert.deepEqual(matrix.years[0].months.map(({ families }) => families[0].status), [
    "not_listed", "not_listed", "not_listed", "not_listed",
    "not_listed", "not_listed", "not_listed", "not_due",
    "not_due", "not_due", "not_due", "not_due",
  ]);
  assert.equal(
    municipalFinanceDocumentCoverageStatusLabel("not_listed"),
    "Não localizado no catálogo consultado",
  );
});

test("converte somente documentos mensais íntegros e falha fechado", () => {
  const document = {
    documentId: "00000000-0000-4000-8000-000000000005",
    sourceResource: "pdc-resumo-execucao-da-receita",
    fiscalYear: 2026,
    referenceMonth: 7,
    documentUrl: "https://barreiras.mtransparente.com.br/receita-2026-07.pdf",
    documentPreserved: true,
    documentArtifactSha256: "b".repeat(64),
    collectedAt: "2026-08-30T12:00:00.000Z",
  };

  assert.deepEqual(toMunicipalFinanceDocumentCoverageEntry(document), {
    documentId: document.documentId,
    resource: document.sourceResource,
    fiscalYear: 2026,
    referenceMonth: 7,
    documentUrl: document.documentUrl,
    documentPreserved: true,
    artifactSha256: "b".repeat(64),
    collectedAt: document.collectedAt,
  });
  assert.equal(toMunicipalFinanceDocumentCoverageEntry({ ...document, referenceMonth: null }), null);
  assert.equal(toMunicipalFinanceDocumentCoverageEntry({ ...document, documentUrl: "http://inseguro.test" }), null);
  assert.equal(buildMunicipalFinanceDocumentCoverage([entry({ resource: "rreo" })]), null);
});

test("payload da rota aceita apenas o contrato completo", () => {
  const valid = { state: "available", entries: [entry()] };
  assert.deepEqual(parseMunicipalFinanceDocumentCoverageApiPayload(valid), valid);
  assert.deepEqual(
    parseMunicipalFinanceDocumentCoverageApiPayload({ state: "unavailable" }),
    { state: "unavailable" },
  );
  assert.equal(
    parseMunicipalFinanceDocumentCoverageApiPayload({
      state: "available",
      entries: [{ ...entry(), unexpected: true }],
    }),
    null,
  );
});
