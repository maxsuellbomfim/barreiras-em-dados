import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parseCguFederalAmendmentDocumentRankingRows,
  parseCguFederalAmendmentDocumentRows,
} from "../../apps/web/lib/cgu-federal-amendment-documents.mjs";

const SHA = "a".repeat(64);
const resourcesPage = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

function documentRow(overrides = {}) {
  return {
    archive_year: 2024,
    amendment_year: 2024,
    amendment_code: "202450410002",
    amendment_number: "0002",
    amendment_type: "Emenda de Comissão",
    author_kind: "commission",
    author_key: "com. da saude",
    author_name: "COM. DA SAUDE",
    document_date: "2024-06-24",
    document_code: "257001000012024OB018682",
    expense_stage: "payment",
    expense_stage_source: "Pagamento",
    committed_amount: "0.00",
    paid_amount: "7500000.00",
    beneficiary_name: "FUNDO MUNICIPAL DE SAUDE DE BARREIRAS",
    beneficiary_type: "FUNDO PUBLICO",
    beneficiary_municipality: "BARREIRAS",
    locality: "BARREIRAS - BA",
    agency_name: "MINISTERIO DA SAUDE",
    superior_agency_name: "MINISTERIO DA SAUDE",
    function_name: "SAUDE",
    subfunction_name: "ASSISTENCIA HOSPITALAR",
    program_name: "ATENCAO ESPECIALIZADA",
    action_name: "CUSTEIO DA SAUDE",
    citizen_language: "Apoio ao custeio da saúde",
    source_row_number: 101,
    source_url:
      "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/2024_EmendasParlamentaresPorDocumento.zip",
    artifact_sha256: SHA,
    collected_at: "2026-08-21T20:00:00+00:00",
    methodology_version: "cgu-federal-amendment-documents/1.0.0",
    ...overrides,
  };
}

function rankingRow(overrides = {}) {
  return {
    rank_position: 1,
    author_kind: "commission",
    author_key: "com. da saude",
    author_name: "COM. DA SAUDE",
    amendment_count: 1,
    document_count: 2,
    committed_amount: "5000000.00",
    paid_amount: "10000000.00",
    first_document_date: "2024-06-12",
    last_document_date: "2024-06-24",
    aggregation_policy: "single_document_source_no_cross_source_sum",
    methodology_version: "cgu-federal-amendment-document-ranking/1.0.0",
    ...overrides,
  };
}

test("documentos da CGU preservam ano da emenda e ano do movimento", () => {
  const parsed = parseCguFederalAmendmentDocumentRows([documentRow()]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].archiveYear, 2024);
  assert.equal(parsed[0].amendmentYear, 2024);
  assert.equal(parsed[0].expenseStage, "payment");
  assert.equal(parsed[0].paidAmount, "7500000.00");
});

test("parser rejeita fase, fonte e metodologia incoerentes", () => {
  assert.equal(
    parseCguFederalAmendmentDocumentRows([
      documentRow({ expense_stage: "transfer" }),
    ]),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentDocumentRows([
      documentRow({ source_url: "http://nao-oficial.example/file.zip" }),
    ]),
    null,
  );
  assert.equal(
    parseCguFederalAmendmentDocumentRows([
      documentRow({ methodology_version: "wrong" }),
    ]),
    null,
  );
});

test("ranking documental valida sequência e não mistura fontes", () => {
  const parsed = parseCguFederalAmendmentDocumentRankingRows([
    rankingRow(),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].paidAmount, "10000000.00");
  assert.equal(
    parseCguFederalAmendmentDocumentRankingRows([
      rankingRow({ aggregation_policy: "sum_all_sources" }),
    ]),
    null,
  );
});

test("página explica a série documental e mantém detalhes recolhidos", () => {
  assert.match(resourcesPage, /Movimentações por documento oficial/);
  assert.match(resourcesPage, /ano do documento pode ser diferente do ano da emenda/);
  assert.match(resourcesPage, /Os valores desta série não são somados/);
  assert.match(resourcesPage, /Conferir documentos, favorecidos e evidências/);
});
