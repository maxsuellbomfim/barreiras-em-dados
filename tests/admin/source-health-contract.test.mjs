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
const progressMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260831160000_admin_collection_work_progress.sql",
    import.meta.url,
  ),
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
test("painel informa a defasagem entre periodo da fonte e tentativa", () => {
  assert.match(component, /formatLag/);
  assert.match(component, /Defasagem/);
  assert.match(component, /Sem atraso/);
});

test("painel separa ultima tentativa da ultima atualizacao valida", () => {
  assert.match(component, /latest_successful_completed_at/);
  assert.match(component, /Última atualização válida/);
  assert.match(component, /Tentativa mais recente/);
});

test("painel mostra alertas de atualidade sem chamar fonte sazonal de atrasada", () => {
  assert.match(component, /Atualizações atrasadas/);
  assert.match(component, /Prazo operacional/);
  assert.match(component, /Situação do prazo/);
  assert.match(component, /formatFreshnessStatus/);
  assert.match(component, /not_monitored/);
});

test("painel expõe somente contadores sanitizados do trabalho retomável", () => {
  assert.match(progressMigration, /create function api\.get_collection_health_v4\(/);
  assert.match(progressMigration, /latest_work_completed integer/);
  assert.match(progressMigration, /latest_work_total integer/);
  assert.match(progressMigration, /latest_work_remaining integer/);
  assert.match(progressMigration, /latest_batch_processed integer/);
  assert.doesNotMatch(progressMigration, /next_after_cnpj/);
  assert.match(component, /Progresso do ciclo/);
  assert.match(component, /formatCollectionWorkProgress/);
  assert.match(page, /get_collection_health_v4/);
  assert.match(page, /error\?\.code === "PGRST202"/);
  assert.match(page, /get_collection_health_v3/);
});
