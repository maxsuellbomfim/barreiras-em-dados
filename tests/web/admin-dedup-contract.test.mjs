import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const queueMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260808160000_admin_queue_dedup_and_alias_count.sql",
    import.meta.url,
  ),
  "utf8",
);
const aliasRepository = await readFile(
  new URL(
    "../../workers/document-processing/src/barreiras_docproc/alias_repository.py",
    import.meta.url,
  ),
  "utf8",
);

test("fila administrativa deduplica o mesmo ato entre artefatos", () => {
  assert.match(
    queueMigration,
    /select distinct on \(\s*candidate\.candidate_type,\s*candidate\.act_number_key,\s*candidate\.act_date_key\s*\)/s,
  );
  assert.match(queueMigration, /extraction-review-queue\/1\.7\.0/);
  assert.match(queueMigration, /candidate\.created_at desc/);
});

test("incidência de alias conta registros oficiais distintos", () => {
  assert.match(
    aliasRepository,
    /count\(distinct authors\.source_record_key\)::integer\s+as item_count/s,
  );
  assert.doesNotMatch(
    aliasRepository,
    /count\(\*\)::integer as item_count/,
  );
});
