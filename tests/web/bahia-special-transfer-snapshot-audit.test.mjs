import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const migrationUrl = new URL(
  "../../supabase/migrations/20260903233000_split_bahia_special_transfer_snapshot_hashes.sql",
  import.meta.url,
);

test("auditoria separa fatos publicos da linhagem renovada a cada coleta", () => {
  assert.equal(existsSync(migrationUrl), true, "migration de hashes ausente");
  const migration = readFileSync(migrationUrl, "utf8");

  assert.match(
    migration,
    /create or replace function territory\.refresh_bahia_special_transfer_payment_snapshot\(\)/,
  );
  assert.match(migration, /live_semantic_manifest text;/);
  assert.match(migration, /snapshot_semantic_manifest text;/);
  assert.match(
    migration,
    /to_jsonb\(source_row\)\s*-\s*'extraction_result_id'\s*-\s*'raw_artifact_id'\s*-\s*'source_artifact_sha256'\s*-\s*'source_collected_at'\s*-\s*'result_created_at'/,
  );
  assert.match(
    migration,
    /snapshot_semantic_manifest is distinct from live_semantic_manifest[\s\S]+raise exception/,
  );
  assert.match(
    migration,
    /'semantic_content_sha256', snapshot_semantic_manifest/,
  );
  assert.match(
    migration,
    /'lineage_content_sha256', snapshot_lineage_manifest/,
  );
  assert.match(
    migration,
    /'content_sha256', snapshot_lineage_manifest/,
    "o campo legado deve continuar representando o hash integral",
  );
  assert.match(
    migration,
    /'semantic_hash_excludes',[\s\S]+'extraction_result_id'[\s\S]+'result_created_at'/,
  );
});

test("hash integral continua protegendo a copia atomica", () => {
  assert.equal(existsSync(migrationUrl), true, "migration de hashes ausente");
  const migration = readFileSync(migrationUrl, "utf8");

  assert.match(migration, /live_lineage_manifest text;/);
  assert.match(migration, /snapshot_lineage_manifest text;/);
  assert.match(
    migration,
    /snapshot_lineage_manifest is distinct from live_lineage_manifest/,
  );
  assert.match(
    migration,
    /'bahia-special-transfer-payment-snapshot\/1\.1\.0'/,
  );
});
