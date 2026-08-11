import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../apps/web/lib/revenues.ts", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("contrato público exige receita validada e documento filho", () => {
  assert.match(source, /public-revenues\/1\.3\.0/);
  assert.match(source, /validation_status/);
  assert.match(source, /document_artifact_sha256/);
  assert.match(source, /collection_direction/);
  assert.match(source, /adjustment/);
  assert.match(source, /-\\?\\d/);
  assert.match(page, /publicado após validação determinística/);
  assert.match(page, /PDF preservado/);
});
