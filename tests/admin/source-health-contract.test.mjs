import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260805121332_admin_collection_health.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/admin/app/page.tsx", import.meta.url),
  "utf8",
);
const component = await readFile(
  new URL("../../apps/admin/app/collection-health.tsx", import.meta.url),
  "utf8",
);

test("saúde das fontes é uma projeção sanitizada e restrita a revisores", () => {
  assert.match(migration, /create function api\.get_collection_health\(/);
  assert.match(migration, /security definer/);
  assert.match(migration, /set search_path = ''/);
  assert.match(migration, /api\.is_active_reviewer\(\)/);
  assert.match(
    migration,
    /revoke all on function api\.get_collection_health\(integer\)\s+from public, anon/,
  );
  assert.match(
    migration,
    /grant execute on function api\.get_collection_health\(integer\)\s+to authenticated/,
  );
  assert.doesNotMatch(migration, /checkpoint/);
  assert.doesNotMatch(migration, /run\.metrics|run\.error_detail/);
});

test("painel distingue ausência de cobertura de fonte comprovadamente vazia", () => {
  assert.match(page, /get_collection_health/);
  assert.match(component, /Saúde das fontes/);
  assert.match(component, /Ainda sem execução controlada/);
  assert.match(component, /não\s+significa que a fonte não tenha dados/i);
  assert.match(component, /Falha mais recente/);
});
