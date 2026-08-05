import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260808200000_historical_representative_registry.sql",
    import.meta.url,
  ),
  "utf8",
);

test("cadastro histórico fica separado do cadastro atual", () => {
  assert.match(migration, /create table if not exists political\.historical_representatives/);
  assert.match(migration, /editorial_status.*source_pending/s);
  assert.match(migration, /mandate_status.*former/s);
  assert.match(migration, /historical_representative_aliases/);
  assert.match(migration, /historical_representative_id uuid/);
});

test("projeção pública só retorna registros aprovados com fonte", () => {
  assert.match(migration, /where historical\.editorial_status = 'approved'/);
  assert.match(migration, /editorial_status <> 'approved'.*source_url/s);
  assert.match(migration, /source_url ~ '\^https:\/\/'/);
  assert.match(migration, /grant execute on function api\.get_historical_representatives/);
});

test("aliases históricos exigem aprovação e mantêm evidência", () => {
  assert.match(migration, /source_suggestion_id uuid/);
  assert.match(migration, /evidence_note text not null/);
  assert.match(migration, /evidence_url ~ '\^https:\/\/'/);
  assert.match(migration, /active = false or approved_by is not null/);
  assert.match(migration, /active = false or approved_at is not null/);
});
