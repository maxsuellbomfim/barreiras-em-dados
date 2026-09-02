import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260803125428_finance_coverage_public_projection.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/finance-coverage.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/financas/page.tsx", import.meta.url), "utf8");
const obligationCoverageClient = await readFile(
  new URL("../../apps/web/lib/public-obligations.mjs", import.meta.url),
  "utf8",
);
const obligationCoverageMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260812022526_official_document_search_evidence.sql",
    import.meta.url,
  ),
  "utf8",
);

test("projeção de cobertura separa ausência de zero", () => {
  assert.match(migration, /get_public_finance_coverage/);
  assert.match(migration, /revenue_only/);
  assert.match(migration, /expense_only/);
  assert.match(migration, /'missing'/);
  assert.match(migration, /não significa receita ou despesa zero/);
  assert.match(migration, /finance-coverage\/1\.0\.0/);
});

test("cliente público valida a metodologia e estados", () => {
  assert.match(client, /finance-coverage\/1\.1\.0/);
  assert.match(client, /PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY/);
  assert.match(client, /coverageStatus/);
});

test("página explica ao cidadão como fonte, correção e ausência são tratadas", () => {
  assert.match(page, /mesmo registro e a mesma URL do PDF oficial/);
  assert.match(page, /fica fora dos totais até a correção/);
  assert.match(page, /A versão anterior permanece no histórico de auditoria/);
  assert.match(page, /nunca significa arrecadação ou gasto zero/);
});

test("página financeira consulta a cobertura no tempo da requisição", () => {
  assert.match(page, /import \{ connection \} from "next\/server"/);
  const requestBoundary = page.indexOf("await connection()");
  const coverageQuery = page.indexOf("getPublicFinanceCoverage()", requestBoundary);
  assert.ok(requestBoundary > -1);
  assert.ok(coverageQuery > requestBoundary);
  assert.doesNotMatch(page, /dynamic\s*=\s*["']force-dynamic["']/);
});

test("lacunas de obrigações distinguem documento, seção ausente e fonte incompleta", () => {
  assert.match(obligationCoverageMigration, /document_not_confirmed/);
  assert.match(obligationCoverageMigration, /section_absent/);
  assert.match(obligationCoverageMigration, /section_incomplete/);
  assert.doesNotMatch(obligationCoverageMigration, /result_payload\s*->>\s*'detail'\s+as/);
  assert.match(obligationCoverageClient, /Isso n\\u00e3o significa valor zero/);
  assert.match(
    obligationCoverageClient,
    /O Barreiras 360 n\\u00e3o estimou nem completou o valor/,
  );
});

test("documento não encontrado exige busca oficial preservada", () => {
  assert.match(obligationCoverageMigration, /official_document_searches/);
  assert.match(obligationCoverageMigration, /document_not_found/);
  assert.match(obligationCoverageMigration, /evidence_manifest_sha256/);
  assert.match(
    obligationCoverageClient,
    /N\\u00e3o encontrado no cat\\u00e1logo oficial/,
  );
  assert.match(obligationCoverageClient, /pode publicar o arquivo depois/);
});

test("restos a pagar mostram leitura rápida e histórico recolhido", () => {
  assert.match(page, /Último mês com valor publicado/);
  assert.match(page, /competências com valor/);
  assert.match(page, /seção ausente/);
  assert.match(page, /fonte incompleta/);
  assert.match(page, /Ver histórico mês a mês/);
  assert.match(page, /não é o total da dívida municipal/);
});
