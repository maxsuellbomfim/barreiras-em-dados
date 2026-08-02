import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/backfill-gazette-acts.yml", import.meta.url),
  "utf8",
);

test("workflow de atos processa acervo preservado e mantém publicação segura", () => {
  assert.match(workflow, /process_gazette_acts/);
  assert.match(workflow, /assist_extraction_candidates/);
  assert.match(workflow, /publish_verified_candidates/);
  assert.match(workflow, /MUNICIPAL_TRANSPARENCY_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /cron: "17 23 \* \* \*"/);
});
