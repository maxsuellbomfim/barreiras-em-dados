import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
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
const blockReasonMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260902052000_admin_collection_block_reason.sql",
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

test("painel explica por que a partição mais recente foi bloqueada", () => {
  assert.match(blockReasonMigration, /create function api\.get_collection_health_v5\(/);
  assert.match(blockReasonMigration, /latest_block_reason text/);
  assert.match(blockReasonMigration, /partition\.block_reason/);
  assert.match(blockReasonMigration, /collection-health\/1\.5\.0/);
  assert.match(
    blockReasonMigration,
    /grant execute on function api\.get_collection_health_v5\(integer\)\s+to authenticated/,
  );
  assert.match(page, /get_collection_health_v5/);
  assert.match(page, /get_collection_health_v4/);
  assert.match(component, /latest_block_reason/);
  assert.match(component, /Motivo do bloqueio/);
});

test("painel recebe progresso documental sanitizado do TCM-BA", async () => {
  const migrationsDirectory = new URL("../../supabase/migrations/", import.meta.url);
  const migrationName = (await readdir(migrationsDirectory)).find((name) =>
    name.endsWith("_admin_tcm_document_progress.sql"),
  );
  assert.ok(migrationName, "a migration de progresso documental deve existir");
  const documentProgressMigration = await readFile(
    new URL(migrationName, migrationsDirectory),
    "utf8",
  );

  assert.match(
    documentProgressMigration,
    /create function api\.get_collection_health_v6\(/,
  );
  assert.match(documentProgressMigration, /latest_work_unit text/);
  assert.match(documentProgressMigration, /'expected_documents'/);
  assert.match(documentProgressMigration, /'preserved_documents'/);
  assert.match(documentProgressMigration, /'remaining_documents'/);
  assert.match(documentProgressMigration, /'documents_downloaded'/);
  assert.match(documentProgressMigration, /partition\.partition_key ~ '\^documents:/);
  assert.match(documentProgressMigration, /parsed\.completed \+ parsed\.remaining = parsed\.total/);
  assert.match(documentProgressMigration, /'collection-health\/1\.6\.0'/);
  assert.match(
    documentProgressMigration,
    /revoke all on function api\.get_collection_health_v6\(integer\)\s+from public, anon/,
  );
  assert.match(page, /get_collection_health_v6/);
  assert.match(page, /get_collection_health_v5/);
  assert.match(component, /latest_work_unit/);
  assert.match(component, /workProgress\.heading/);
});

test("painel mede somente lotes agendados documentalmente íntegros", async () => {
  const migrationsDirectory = new URL("../../supabase/migrations/", import.meta.url);
  const migrationName = (await readdir(migrationsDirectory)).find((name) =>
    name.endsWith("_admin_tcm_scheduled_streak.sql"),
  );
  assert.ok(migrationName, "a migration da sequência agendada deve existir");
  const streakMigration = await readFile(
    new URL(migrationName, migrationsDirectory),
    "utf8",
  );

  assert.match(streakMigration, /create function api\.get_collection_health_v7\(/);
  assert.match(streakMigration, /scheduled_success_streak integer/);
  assert.match(streakMigration, /scheduled_runs_observed integer/);
  assert.match(streakMigration, /latest_scheduled_run_at timestamptz/);
  assert.match(streakMigration, /execution_origin' = 'windows_scheduler'/);
  assert.match(streakMigration, /documents_preserved_before/);
  assert.match(streakMigration, /documents_preserved_after/);
  assert.match(streakMigration, /documents_remaining/);
  assert.match(streakMigration, /expected_documents/);
  assert.match(streakMigration, /coalesce\([\s\S]*false[\s\S]*as is_valid/);
  assert.match(streakMigration, /collection-health\/1\.7\.0/);
  assert.match(streakMigration, /collection_runs_tcm_scheduler_recent_idx/);
  assert.match(
    streakMigration,
    /revoke all on function api\.get_collection_health_v7\(integer\)\s+from public, anon/,
  );
  assert.match(page, /get_collection_health_v7/);
  assert.match(page, /get_collection_health_v6/);
  assert.match(component, /scheduled_success_streak/);
  assert.match(component, /Execuções agendadas verificáveis/);
});
