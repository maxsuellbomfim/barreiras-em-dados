import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260813151023_register_bahia_state_amendments.sql",
    import.meta.url,
  ),
  "utf8",
);
const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);
const dataSources = await readFile(
  new URL("../../docs/DATA_SOURCES.md", import.meta.url),
  "utf8",
);

test("fonte estadual fica privada e separada das emendas federais", () => {
  assert.match(migration, /'bahia-open-data'/);
  assert.match(migration, /'state-parliamentary-amendments'/);
  assert.match(migration, /'bahia\/emendas-estaduais\/'/);
  assert.doesNotMatch(migration, /grant\s+(?:select|execute)[\s\S]+\bto\s+anon\b/i);
  assert.match(migration, /territorial_scope[^\n]+not_available_in_archive/);
});

test("workflow agenda preservacao do catalogo e ZIP sem publicar ranking", () => {
  assert.match(workflow, /include_bahia_state_amendments:/);
  assert.match(
    workflow,
    /barreiras_collectors\.commands\.collect_bahia_state_amendments/,
  );
  assert.doesNotMatch(workflow, /publish_bahia_state_amendment/i);
});

test("documentacao declara o limite territorial observado na fonte", () => {
  assert.match(dataSources, /cinco CSVs/i);
  assert.match(dataSources, /n.o publica(?:m)? coluna municipal\s+expl.cita/i);
  assert.match(dataSources, /n.o autoriza atribui..o a Barreiras/i);
});
