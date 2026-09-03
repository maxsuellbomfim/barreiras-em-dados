import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const migrationUrl = new URL(
  "../../supabase/migrations/20260903133000_materialize_bahia_state_loa_source.sql",
  import.meta.url,
);

test("materializa a fonte validada e mantém o JSON bruto fora da leitura pública", () => {
  assert.equal(existsSync(migrationUrl), true, "migration do snapshot ausente");
  const migration = readFileSync(migrationUrl, "utf8");

  assert.match(
    migration,
    /alter view territory\.bahia_state_loa_amendments\s+rename to bahia_state_loa_amendments_live/,
  );
  assert.match(
    migration,
    /create table territory\.bahia_state_loa_amendment_snapshot[\s\S]+with no data/,
  );
  assert.match(
    migration,
    /create function territory\.refresh_bahia_state_loa_amendment_snapshot\(\)/,
  );
  assert.match(
    migration,
    /insert into territory\.bahia_state_loa_amendment_snapshot[\s\S]+from territory\.bahia_state_loa_amendments_live/,
  );
  assert.match(
    migration,
    /create view territory\.bahia_state_loa_amendments[\s\S]+from territory\.bahia_state_loa_amendment_snapshot/,
  );
  assert.match(
    migration,
    /force row level security[\s\S]+revoke all on table[\s\S]+from public, anon, authenticated/,
  );
  assert.match(
    migration,
    /grant execute on function[\s\S]+refresh_bahia_state_loa_amendment_snapshot\(\)[\s\S]+to collector_worker/,
  );
  assert.doesNotMatch(
    migration,
    /grant select[^;]+bahia_state_loa_amendment_snapshot[^;]+to (?:anon|authenticated)/,
  );
});

test("a migration popula o snapshot antes de entregar a view leve", () => {
  assert.equal(existsSync(migrationUrl), true, "migration do snapshot ausente");
  const migration = readFileSync(migrationUrl, "utf8");
  const refreshIndex = migration.indexOf(
    "select territory.refresh_bahia_state_loa_amendment_snapshot();",
  );
  const projectionIndex = migration.indexOf(
    "create view territory.bahia_state_loa_amendments",
  );

  assert.ok(refreshIndex >= 0);
  assert.ok(projectionIndex > refreshIndex);
});

test("toda reconciliação atualiza primeiro a fonte normalizada", () => {
  assert.equal(existsSync(migrationUrl), true, "migration do snapshot ausente");
  const migration = readFileSync(migrationUrl, "utf8");
  const cascadeStart = migration.indexOf(
    "create or replace function territory.refresh_bahia_state_loa_execution_reconciliation_snapshot()",
  );
  const sourceRefresh = migration.indexOf(
    "perform territory.refresh_bahia_state_loa_amendment_snapshot();",
    cascadeStart,
  );
  const reconciliationRefresh = migration.indexOf(
    "delete from territory.bahia_state_loa_execution_reconciliation_snapshot;",
    cascadeStart,
  );

  assert.ok(cascadeStart >= 0);
  assert.ok(sourceRefresh > cascadeStart);
  assert.ok(reconciliationRefresh > sourceRefresh);
});

test("o refresh aborta se contagem ou conteúdo divergirem da fonte canônica", () => {
  assert.equal(existsSync(migrationUrl), true, "migration do snapshot ausente");
  const migration = readFileSync(migrationUrl, "utf8");

  assert.match(migration, /live_manifest text;/);
  assert.match(migration, /snapshot_manifest text;/);
  assert.match(
    migration,
    /jsonb_agg\([\s\S]+to_jsonb\(source_row\)[\s\S]+extensions\.digest/,
  );
  assert.match(migration, /public\.digest/);
  assert.match(
    migration,
    /if refreshed_rows <> live_rows[\s\S]+snapshot_manifest is distinct from live_manifest[\s\S]+raise exception/,
  );
});
