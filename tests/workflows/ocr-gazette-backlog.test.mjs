import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/ocr-gazette-backlog.yml", import.meta.url),
  "utf8",
);

test("dreno de OCR processa em lote e republica as edições que ganharam texto", () => {
  assert.match(workflow, /cron: "47,17 \* \* \* \*"/);
  assert.match(workflow, /tesseract-ocr-por/);
  assert.match(workflow, /LIMIT_PAGES: \$\{\{ inputs\.limit_pages \|\| '200' \}\}/);
  assert.match(workflow, /--limit-pages "\$\{LIMIT_PAGES\}"/);
  assert.doesNotMatch(workflow, /--limit-pages "\$\{\{ inputs\./);
  // OCR sem republicação deixaria o texto novo preso no acervo bruto.
  assert.ok(
    workflow.indexOf("ocr_gazette_pages") < workflow.indexOf("segment_gazette_editions"),
  );
  assert.match(workflow, /QUERIDO_DIARIO_SUPABASE_WORKLOAD_PASSWORD/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /permissions:\s*\n\s*contents: read/);
});
