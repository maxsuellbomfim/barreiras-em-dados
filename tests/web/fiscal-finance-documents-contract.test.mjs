import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260811031818_fiscal_documents_metadata.sql",
    import.meta.url,
  ),
  "utf8",
);
const obligationMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260811161731_public_financial_obligation_documents.sql",
    import.meta.url,
  ),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/finance-documents.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/financas/page.tsx", import.meta.url), "utf8");

test("catalogo fiscal usa ano_ref e informacoes de RREO/RGF", () => {
  assert.match(migration, /coalesce\(candidate\.payload ->> 'ano', candidate\.payload ->> 'ano_ref'\)/);
  assert.match(migration, /candidate\.payload ->> 'informacoes'/);
  assert.match(migration, /public-finance-documents\/1\.2\.0/);
  assert.match(migration, /RREO\/RGF/);
});

test("cliente valida a nova versao do catalogo fiscal", () => {
  assert.match(client, /public-finance-documents\/1\.3\.0/);
});

test("projecao publica inclui RGF e documentos de obrigacoes sem inferir saldo", () => {
  assert.match(obligationMigration, /municipal_transparency_rgf/);
  assert.match(obligationMigration, /municipal_transparency_balancetes/);
  assert.match(obligationMigration, /municipal_transparency_pdc-contas-anuais/);
  assert.match(obligationMigration, /public-finance-documents\/1\.3\.0/);
  assert.match(client, /public-finance-documents\/1\.3\.0/);
  assert.match(page, /Dívidas e obrigações em apuração/);
  assert.match(page, /não\s+representa o total da dívida municipal/);
});

test("interface separa demonstrativos fiscais de fechamentos mensais", () => {
  assert.match(page, /isFiscalDocument/);
  assert.match(page, /RREO e RGF: a vis[aã]o fiscal mais ampla/);
  assert.match(page, /não substituem o fechamento mensal/);
});
