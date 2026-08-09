import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/collect-finance-documents.yml", import.meta.url),
  "utf8",
);

test("coleta financeira respeita o orçamento de conexões", () => {
  assert.match(workflow, /max-parallel:\s*1/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /--download-documents/);
});

test("coleta financeira permite backfill por recurso e documentos grandes", () => {
  assert.match(workflow, /resource:/);
  assert.match(workflow, /pdc-resumo-execucao-da-despesa/);
  assert.match(workflow, /max_pages:[\s\S]*- \"50\"/);
  assert.match(workflow, /- name: Preservar documento financeiro[\s\S]*if: \$\{\{ inputs\.resource == 'all'/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_MAX_DOCUMENT_BYTES: \"268435456\"/);
});
