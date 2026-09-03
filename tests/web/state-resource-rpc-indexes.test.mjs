import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const migrationPath = new URL(
  "../../supabase/migrations/20260903125418_index_state_resource_rpc_sources.sql",
  import.meta.url,
);

test("indexa em conjunto as duas versoes validas da LOA estadual", () => {
  const migration = readFileSync(migrationPath, "utf8");

  assert.match(
    migration,
    /create index extraction_results_bahia_state_loa_all_valid_idx/i,
  );
  assert.match(
    migration,
    /extractor_version\s*=\s*any\s*\(array\[\s*'bahia-state-loa-barreiras\/1\.1\.0'::text,\s*'bahia-state-loa-barreiras\/1\.2\.0'::text\s*\]\)/i,
  );
  assert.match(
    migration,
    /candidate_type\s*=\s*'bahia_state_loa_authorized_amendment'/i,
  );
});

test("indexa os pagamentos estaduais especiais antes da deduplicacao", () => {
  const migration = readFileSync(migrationPath, "utf8");

  assert.match(
    migration,
    /create index extraction_results_bahia_special_transfer_payment_valid_idx/i,
  );
  assert.match(migration, /result_payload\s*->>\s*'payment_id'/i);
  assert.match(migration, /result_payload\s*->>\s*'source_collected_at'/i);
  assert.match(
    migration,
    /candidate_type\s*=\s*'bahia_special_transfer_payment_candidate'/i,
  );
});
