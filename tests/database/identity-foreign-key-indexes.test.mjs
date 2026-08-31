import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migrationUrl = new URL(
  "../../supabase/migrations/20260831170000_index_identity_foreign_keys.sql",
  import.meta.url,
);

test("identity evidence foreign keys have dedicated covering indexes", async () => {
  const migration = await readFile(migrationUrl, "utf8");
  const executableSql = migration.replace(/--.*$/gm, "");
  const expectedIndexes = [
    ["identity", "person_aliases", "origin_raw_artifact_id"],
    ["identity", "person_aliases", "origin_raw_record_id"],
    ["identity", "person_source_links", "origin_raw_record_id"],
    ["identity", "person_source_links", "source_evidence_id"],
    ["private", "person_identifier_conflicts", "existing_person_id"],
    ["private", "person_identifier_gaps", "origin_raw_record_id"],
    ["private", "person_identifiers", "origin_raw_artifact_id"],
    ["private", "person_identifiers", "origin_raw_record_id"],
  ];

  for (const [schema, table, column] of expectedIndexes) {
    assert.match(
      migration,
      new RegExp(
        `create index [a-z0-9_]+\\s+on ${schema}\\.${table} \\(\\s*${column}\\s*\\)`,
        "i",
      ),
      `${schema}.${table}.${column} precisa de indice dedicado`,
    );
  }

  assert.equal((migration.match(/\bcreate index\b/gi) ?? []).length, 8);
  assert.doesNotMatch(executableSql, /drop\s+(?:index|table|column)/i);
  assert.doesNotMatch(
    executableSql,
    /encrypted_value|fingerprint|last_four/i,
  );
});
