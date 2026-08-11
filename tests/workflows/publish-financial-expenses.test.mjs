import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL(
    "../../.github/workflows/publish-financial-expenses.yml",
    import.meta.url,
  ),
  "utf8",
);

test("workflow de despesas usa o publicador versionado e limite seguro", () => {
  assert.match(workflow, /publish_expense_reports/);
  assert.match(workflow, /publish_public_obligations/);
  assert.match(workflow, /default: "5"/);
  assert.match(workflow, /timeout-minutes: 120/);
  assert.match(workflow, /--fiscal-year-from/);
  assert.match(workflow, /--fiscal-year-to/);
  assert.match(workflow, /--limit/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /\[postgres,storage,pdf,ocr\]/);
  assert.match(workflow, /dry_run_public_obligations:/);
  assert.match(workflow, /inputs\.dry_run_public_obligations != true/);
  assert.match(workflow, /--dry-run/);
});
