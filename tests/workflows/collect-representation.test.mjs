import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-representation.yml", import.meta.url),
  "utf8",
);

test("representação tenta todas as fontes antes de consolidar o resultado", () => {
  for (const stepId of ["federal", "municipal", "state", "executive", "elections"]) {
    assert.match(workflow, new RegExp(`id: ${stepId}[\\s\\S]*?continue-on-error: true`));
    assert.match(workflow, new RegExp(`steps\\.${stepId}\\.outcome`));
  }
  assert.match(workflow, /Consolidar resultado sem ocultar falhas/);
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(workflow, /exit 1/);
});

test("resultado dos passos entra no shell apenas por variáveis de ambiente", () => {
  const outcomeLines = workflow
    .split("\n")
    .filter((line) => line.includes("${{ steps.") && line.includes(".outcome }}"));
  assert.equal(outcomeLines.length, 5);
  assert.ok(outcomeLines.every((line) => line.includes("_OUTCOME:")));
  assert.match(workflow, /FEDERAL_OUTCOME: \$\{\{ steps\.federal\.outcome \}\}/);
  assert.match(workflow, /"\$FEDERAL_OUTCOME"/);
});
