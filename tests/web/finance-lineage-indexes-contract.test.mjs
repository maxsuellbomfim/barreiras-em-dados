import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const migrationsDir = new URL("../../supabase/migrations/", import.meta.url);
const indexes = await readFile(
  new URL("20260923163702_finance_lineage_indexes.sql", migrationsDir),
  "utf8",
);

// A definição vigente da função é a da migration mais recente que a cria.
const files = (await readdir(migrationsDir)).sort();
let lineage = "";
for (const file of files) {
  const sql = await readFile(new URL(file, migrationsDir), "utf8");
  if (sql.includes("function finance.get_exact_document_lineage_pairs()")) {
    lineage = sql;
  }
}

test("os índices espelham os predicados da linhagem financeira vigente", () => {
  assert.ok(lineage, "a função de linhagem precisa existir nas migrations");
  // Sem este par, cada documento municipal lê a página inteira de registros.
  assert.match(indexes, /on raw\.raw_records \(raw_artifact_id, source_record_key\)/);
  assert.match(lineage, /document\.metadata ->> 'source_record_key'\s*= origin\.source_record_key/);
  // Sem este predicado, a linhagem TCM-BA varre os 177 mil registros do catálogo.
  for (const predicate of [
    /record_type = 'tcm_ba_monthly_document'/,
    /left\((?:origin\.)?payload ->> 'category', 8\)\s*in \('PCMGE015', 'PCMGE016'\)/,
  ]) {
    assert.match(indexes, predicate);
    assert.match(lineage, predicate);
  }
});
