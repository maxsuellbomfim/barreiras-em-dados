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
const gitignore = await readFile(new URL("../../.gitignore", import.meta.url), "utf8");

test("fonte estadual fica privada e separada das emendas federais", () => {
  assert.match(migration, /'bahia-open-data'/);
  assert.match(migration, /'state-parliamentary-amendments'/);
  assert.match(migration, /'bahia\/emendas-estaduais\/'/);
  assert.doesNotMatch(migration, /grant\s+(?:select|execute)[\s\S]+\bto\s+anon\b/i);
  assert.match(migration, /territorial_scope[^\n]+not_available_in_archive/);
});

test("workflow agenda preservacao do catalogo e ZIP sem publicar ranking", () => {
  const [jobsBeforeStateCollector, stateCollectorJob] = workflow.split(
    /\n  bahia_state_amendments:/,
  );

  assert.match(workflow, /include_bahia_state_amendments:/);
  assert.ok(stateCollectorJob, "o job estadual deve existir");
  assert.match(
    stateCollectorJob,
    /barreiras_collectors\.commands\.collect_bahia_state_amendments/,
  );
  assert.match(stateCollectorJob, /BAHIA_STATE_TLS_CA_BUNDLE:/);
  assert.match(
    gitignore,
    /!config\/certificates\/sectigo-public-server-authentication-ov-r36-chain\.pem/,
  );
  assert.match(
    stateCollectorJob,
    /729b16d606ab35a0ca027fce556f9b35913d4553f1f9b6e88ba331625519d333[\s\S]+sectigo-public-server-authentication-ov-r36-chain\.pem[\s\S]+sha256sum --check --strict/,
  );
  assert.doesNotMatch(jobsBeforeStateCollector, /BAHIA_STATE_TLS_CA_BUNDLE:/);
  assert.doesNotMatch(workflow, /publish_bahia_state_amendment/i);
});

test("documentacao declara o limite territorial observado na fonte", () => {
  assert.match(dataSources, /cinco CSVs/i);
  assert.match(dataSources, /n.o publica(?:m)? coluna municipal\s+expl.cita/i);
  assert.match(dataSources, /n.o autoriza atribui..o a Barreiras/i);
});
