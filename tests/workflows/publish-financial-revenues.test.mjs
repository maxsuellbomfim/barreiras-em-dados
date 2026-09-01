import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/publish-financial-revenues.yml", import.meta.url),
  "utf8",
);

test("workflow financeiro usa o publicador versionado e limites", () => {
  assert.match(workflow, /publish_revenue_reports/);
  assert.match(workflow, /--fiscal-year-from/);
  assert.match(workflow, /--fiscal-year-to/);
  assert.match(workflow, /--limit/);
  assert.match(workflow, /GITHUB_EVENT_NAME/);
  assert.match(workflow, /--require-artifact/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /python-version: "3\.12"/);
});
