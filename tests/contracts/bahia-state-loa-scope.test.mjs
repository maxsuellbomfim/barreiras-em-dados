import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260814034000_register_bahia_state_loa_scope.sql",
    import.meta.url,
  ),
  "utf8",
);
const schema = JSON.parse(
  await readFile(
    new URL(
      "../../packages/data-contracts/schemas/bahia-state-loa-2026-scope-row.schema.json",
      import.meta.url,
    ),
    "utf8",
  ),
);
const repository = await readFile(
  new URL(
    "../../workers/document-processing/src/barreiras_docproc/bahia_state_loa_repository.py",
    import.meta.url,
  ),
  "utf8",
);

test("indice estadual da LOA permanece privado e consultavel por chave", () => {
  assert.match(migration, /bahia_state_loa_2026_scope_key_idx/);
  assert.match(migration, /bahia_state_loa_2026_scope_row/);
  assert.match(migration, /private_reconciliation_scope/);
  assert.match(migration, /statewide_scope_index/);
  assert.doesNotMatch(migration, /grant\s+(?:select|execute)[\s\S]+\bto\s+anon\b/i);
});

test("contrato do universo nao inventa municipio nem valor", () => {
  assert.equal(schema.properties.parser_version.const, "bahia-state-loa-scope/1.0.0");
  assert.equal(schema.properties.visibility.const, "private_reconciliation_scope");
  assert.ok(!("municipality" in schema.properties));
  assert.ok(!("authorized_amount" in schema.properties));
  assert.match(repository, /['"]bahia_state_loa_2026_scope_row['"]/);
  assert.match(repository, /jsonb_array_elements\(%s::jsonb\)/);
  assert.match(repository, /"extractor_version": scope_row\.parser_version/);
});
