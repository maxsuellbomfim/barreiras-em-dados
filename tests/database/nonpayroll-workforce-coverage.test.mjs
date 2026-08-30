import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migrationUrl = new URL(
  "../../supabase/migrations/20260830030000_public_nonpayroll_workforce_coverage.sql",
  import.meta.url,
);
const lineageFixUrl = new URL(
  "../../supabase/migrations/20260830033000_fix_nonpayroll_workforce_lineage.sql",
  import.meta.url,
);

test("projeção separada expõe apenas cobertura de estagiários e terceirizados", async () => {
  const migration = await readFile(migrationUrl, "utf8");

  assert.match(
    migration,
    /create function api\.get_public_nonpayroll_workforce_coverage\(/,
  );
  assert.match(migration, /record\.payload ->> 'tipo' in \('3', '4'\)/);
  assert.match(migration, /relacao de estagiarios/);
  assert.match(migration, /relacao de terceirizados/);
  assert.match(
    migration,
    /when normalized_title\.value = 'relacao de estagiarios'/,
  );
  assert.match(migration, /'interns'/);
  assert.match(migration, /'outsourced_workers'/);
  assert.match(migration, /'document_preserved'/);
  assert.match(migration, /'catalogued'/);
  assert.match(migration, /'not_listed'/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(
    migration,
    /grant execute on function api\.get_public_nonpayroll_workforce_coverage\(integer\)[\s\S]*to anon, authenticated/,
  );
  assert.doesNotMatch(migration, /->>\s*'(?:cpf|nome|banco|agencia|conta)'/i);
  assert.doesNotMatch(migration, /\b(?:gross|net|deduction|amount)_amount\b/i);
});

test("projeção não limita o catálogo ao collection_run mais recente", async () => {
  const migration = await readFile(lineageFixUrl, "utf8");

  assert.match(
    migration,
    /create or replace function api\.get_public_nonpayroll_workforce_coverage\(/,
  );
  assert.match(
    migration,
    /from raw\.raw_records as record[\s\S]*join raw\.raw_artifacts as origin_artifact[\s\S]*on origin_artifact\.id = record\.raw_artifact_id/,
  );
  assert.doesNotMatch(
    migration,
    /origin_artifact\.collection_run_id = catalog\.collection_run_id/,
  );
  assert.match(migration, /'nonpayroll-workforce-coverage\/1\.0\.1'/);
});
