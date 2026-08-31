import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflowUrl = new URL("../../.github/workflows/ci.yml", import.meta.url);

test("CI executa a suíte Node completa antes dos builds", async () => {
  const workflow = await readFile(workflowUrl, "utf8");

  assert.match(workflow, /- name: Testar Node[\s\S]*?run: pnpm test/);
});

test("CI usa pnpm/action-setup assinado e compatível com Node 24", async () => {
  const workflow = await readFile(workflowUrl, "utf8");

  assert.match(
    workflow,
    /pnpm\/action-setup@0ebf47130e4866e96fce0953f49152a61190b271 # v6\.0\.9/,
  );
  assert.doesNotMatch(
    workflow,
    /pnpm\/action-setup@f40ffcd9367d9f12939873eb1018b921a783ffaa/,
  );
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
