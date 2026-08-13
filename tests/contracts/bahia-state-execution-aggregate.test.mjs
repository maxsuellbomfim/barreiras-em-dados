import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const schemaUrl = new URL(
  "../../packages/data-contracts/schemas/bahia-state-execution-aggregate.schema.json",
  import.meta.url,
);

test("contrato estadual preserva estágios financeiros e limite territorial", async () => {
  let schema;
  try {
    schema = JSON.parse(await readFile(schemaUrl, "utf8"));
  } catch {
    assert.fail("o contrato da execução estadual ainda não existe");
  }

  assert.equal(schema.additionalProperties, false);
  assert.deepEqual(schema.properties.territorial_scope.enum, [
    "not_available_in_execution_archive",
  ]);
  for (const field of [
    "initial_budget_amount",
    "current_budget_amount",
    "committed_amount",
    "liquidated_amount",
    "paid_amount",
  ]) {
    assert.equal(schema.properties[field].type, "string");
    assert.equal(schema.properties[field].pattern, "^-?\\d+\\.\\d{2}$");
    assert.ok(schema.required.includes(field));
  }
  assert.equal(schema.properties.source_artifact_sha256.pattern, "^[a-f0-9]{64}$");
  assert.equal(schema.properties.evidence_sha256.pattern, "^[a-f0-9]{64}$");
});
