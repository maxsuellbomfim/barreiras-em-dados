import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  groupFederalTransferSourceCoverage,
  parseFederalTransferSourceCoverageRows,
} from "../../apps/web/lib/federal-transfer-source-coverage.mjs";

const migration = readFileSync(
  new URL(
    "../../supabase/migrations/20260821025440_public_federal_transfer_source_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);
const territorialScopeFix = readFileSync(
  new URL(
    "../../supabase/migrations/20260821030535_fix_federal_coverage_territorial_scope.sql",
    import.meta.url,
  ),
  "utf8",
);
const documentCoverage = readFileSync(
  new URL(
    "../../supabase/migrations/20260822070000_include_cgu_documents_in_federal_coverage.sql",
    import.meta.url,
  ),
  "utf8",
);
const methodology = readFileSync(
  new URL("../../docs/PARLIAMENTARY_TRANSFERS_METHODOLOGY.md", import.meta.url),
  "utf8",
);
const resourcesPage = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

function coverageRow(overrides = {}) {
  return {
    source_key: "cgu_execution",
    fiscal_year: 2023,
    coverage_status: "observed",
    record_count: 1,
    last_attempted_at: "2026-08-20T05:37:36.896583+00:00",
    source_url:
      "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO",
    methodology_version: "federal-transfer-source-coverage/1.0.0",
    ...overrides,
  };
}

test("cobertura federal aceita somente estados e evidências coerentes", () => {
  const parsed = parseFederalTransferSourceCoverageRows([
    coverageRow(),
    coverageRow({
      source_key: "transferegov_historical",
      fiscal_year: 2022,
      coverage_status: "empty",
      record_count: 0,
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_emenda.zip",
    }),
    coverageRow({
      source_key: "transferegov_current",
      fiscal_year: 2021,
      coverage_status: "failed",
      record_count: null,
      source_url:
        "https://api-publica.transferegov.gestao.gov.br/parcerias/proposta",
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed.length, 3);
  assert.equal(parsed[1].recordCount, 0);
  assert.equal(parsed[2].recordCount, null);
});

test("cobertura rejeita duplicidade, HTTP e zero fabricado", () => {
  assert.equal(
    parseFederalTransferSourceCoverageRows([
      coverageRow(),
      coverageRow(),
    ]),
    null,
  );
  assert.equal(
    parseFederalTransferSourceCoverageRows([
      coverageRow({ source_url: "http://example.test/emendas.zip" }),
    ]),
    null,
  );
  assert.equal(
    parseFederalTransferSourceCoverageRows([
      coverageRow({ coverage_status: "unclassified", record_count: 0 }),
    ]),
    null,
  );
});

test("agrupamento mantém as quatro fontes e anos recentes primeiro", () => {
  const parsed = parseFederalTransferSourceCoverageRows([
    coverageRow({ fiscal_year: 2022 }),
    coverageRow({ fiscal_year: 2023 }),
    coverageRow({
      source_key: "cgu_documents",
      fiscal_year: 2023,
    }),
    coverageRow({
      source_key: "transferegov_current",
      fiscal_year: 2023,
    }),
  ]);
  assert.notEqual(parsed, null);
  const groups = groupFederalTransferSourceCoverage(parsed);
  assert.deepEqual(groups.map((group) => group.fiscalYear), [2023, 2022]);
  assert.deepEqual(
    groups[0].sources.map((source) => source.sourceKey),
    ["cgu_execution", "cgu_documents", "transferegov_current"],
  );
});

test("nova cobertura distingue documentos anuais do retrato agregado da CGU", () => {
  const parsed = parseFederalTransferSourceCoverageRows([
    coverageRow({
      source_key: "cgu_documents",
      fiscal_year: 2026,
      record_count: 2,
      source_url:
        "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares-documentos/2026",
      methodology_version: "federal-transfer-source-coverage/2.0.0",
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].sourceKey, "cgu_documents");
  assert.equal(parsed[0].recordCount, 2);
  assert.match(documentCoverage, /federal-amendment-documents-open-data/);
  assert.match(documentCoverage, /territory\.cgu_federal_amendment_documents/);
  assert.match(documentCoverage, /'cgu_documents'/);
  assert.match(documentCoverage, /federal-transfer-source-coverage\/2\.0\.0/);
});

test("migration publica somente cobertura agregada e sanitizada", () => {
  assert.match(migration, /api\.get_public_federal_transfer_source_coverage/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(migration, /revoke all on function[\s\S]+from public/);
  assert.match(migration, /grant execute on function[\s\S]+to anon, authenticated/);
  assert.doesNotMatch(migration, /checkpoint\s+jsonb/);
  assert.doesNotMatch(migration, /error_detail/);
});

test("correção territorial conta somente emendas históricas confirmadas", () => {
  assert.match(territorialScopeFix, /federal_transfer_proposal_scope as scope/);
  assert.match(territorialScopeFix, /scope\.is_confirmed_for_barreiras/);
  assert.match(territorialScopeFix, /historical_parliamentary_amendments as amendment[\s\S]+join territory\.federal_transfer_proposal_scope/);
  assert.match(methodology, /três\s+linhas confirmadas/);
  assert.match(methodology, /seis linhas regionais excluídas/);
});

test("página explica cobertura sem converter ausência em zero financeiro", () => {
  assert.match(resourcesPage, /Quais anos cada fonte federal já conferiu/);
  assert.match(resourcesPage, /nenhuma linha atribuída a Barreiras/);
  assert.match(resourcesPage, /não significa valor financeiro zero/);
  assert.match(resourcesPage, /Cadastrar o proponente em Barreiras, sozinho, não/);
  assert.match(resourcesPage, /Documentos anuais · CGU/);
  assert.match(resourcesPage, /Cobertura anual das quatro séries federais consultadas/);
  assert.match(resourcesPage, /getPublicFederalTransferSourceCoverage/);
});
