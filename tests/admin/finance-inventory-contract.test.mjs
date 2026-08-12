import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL("../../supabase/migrations/20260803101021_monthly_finance_closure_and_inventory.sql", import.meta.url),
  "utf8",
);
const balanceteStatusMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260812112530_admin_balancete_publication_status.sql",
    import.meta.url,
  ),
  "utf8",
);
const sourceStatusMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260812121448_admin_finance_source_status.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/admin/app/page.tsx", import.meta.url),
  "utf8",
);

test("inventário financeiro é restrito a revisores e mostra o último erro", () => {
  assert.match(migration, /get_finance_ingestion_inventory/);
  assert.match(migration, /api\.is_active_reviewer\(\)/);
  assert.match(migration, /latest_error_detail/);
  assert.match(page, /Documentos financeiros/);
  assert.match(page, /Preservado — ainda não processado/);
  assert.match(page, /latest_error_detail/);
});

test("painel financeiro mostra os fechamentos mensais retornados pela API", () => {
  assert.match(page, /get_public_monthly_finance_closures/);
  assert.match(page, /finance-closure-list/);
  assert.match(page, /operational_difference_amount/);
  assert.match(page, /recalcula\s+totais/);
});

test("inventário reconhece balancetes com obrigações públicas validadas", () => {
  assert.match(balanceteStatusMigration, /'balancetes'/);
  assert.match(balanceteStatusMigration, /finance\.public_obligations/);
  assert.match(
    balanceteStatusMigration,
    /obligation\.source_document_artifact_id\s*=\s*document\.id/,
  );
  assert.match(
    balanceteStatusMigration,
    /obligation\.validation_state\s+in\s*\(\s*'validated',\s*'reconciled'\s*\)/,
  );
  assert.match(balanceteStatusMigration, /obligation_rows\.count/);
  assert.match(balanceteStatusMigration, /'published'::text/);
  assert.match(
    balanceteStatusMigration,
    /finance-ingestion-inventory\/1\.1\.0/,
  );
});

test("inventário distingue seção ausente de documento oficial incompleto", () => {
  assert.match(sourceStatusMigration, /public_obligation_section_absent/);
  assert.match(sourceStatusMigration, /public_obligation_section_incomplete/);
  assert.match(sourceStatusMigration, /'source_absent'::text/);
  assert.match(sourceStatusMigration, /'source_incomplete'::text/);
  assert.match(sourceStatusMigration, /finance-ingestion-inventory\/1\.2\.0/);
  assert.match(page, /Seção não encontrada no documento oficial/);
  assert.match(page, /Documento oficial incompleto/);
  assert.match(page, /source_absent/);
  assert.match(page, /source_incomplete/);
});
