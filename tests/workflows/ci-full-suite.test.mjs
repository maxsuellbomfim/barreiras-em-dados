import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflowUrl = new URL("../../.github/workflows/ci.yml", import.meta.url);

test("CI executa a suíte Node completa antes dos builds", async () => {
  const workflow = await readFile(workflowUrl, "utf8");

  assert.match(workflow, /- name: Testar Node[\s\S]*?run: pnpm test/);
});

test("CI importa e verifica o domínio privado de reconciliação", async () => {
  const workflow = await readFile(workflowUrl, "utf8");

  assert.match(
    workflow,
    /PYTHONPATH: workers\/collectors\/src:workers\/document-processing\/src:workers\/normalization\/src:workers\/reconciliation\/src/,
  );
  assert.match(
    workflow,
    /ruff check[\s\S]*?workers\/reconciliation\/src[\s\S]*?tests/,
  );
});
