import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const collectWorkflow = await readFile(
  new URL("../../.github/workflows/collect-querido-diario.yml", import.meta.url),
  "utf8",
);
const backfillWorkflow = await readFile(
  new URL("../../.github/workflows/backfill-gazette-acts.yml", import.meta.url),
  "utf8",
);

test("coleta diária organiza o integral sem depender de IA", () => {
  assert.match(collectWorkflow, /segment_gazette_editions/);
  assert.doesNotMatch(collectWorkflow, /digest_gazette_editions/);
  assert.match(collectWorkflow, /INTEGRAL_LIMIT: \$\{\{ inputs\.integral_limit \|\| '6' \}\}/);
  assert.match(collectWorkflow, /--limit "\$\{INTEGRAL_LIMIT\}"/);
  const segmentStart = collectWorkflow.indexOf("segment_gazette_editions");
  const segmentBlock = collectWorkflow.slice(Math.max(0, segmentStart - 300), segmentStart + 300);
  assert.doesNotMatch(segmentBlock, /GROQ_API_KEY|OPENROUTER_API_KEY|GEMINI_API_KEY|NVIDIA_API_KEY/);
});

test("backfill preserva o bruto e retoma por limites independentes", () => {
  assert.match(backfillWorkflow, /segment_gazette_editions/);
  assert.match(backfillWorkflow, /integral_limit/);
  assert.match(backfillWorkflow, /PERSISTENCE_MODE: postgres-supabase/);
  assert.match(backfillWorkflow, /SUPABASE_RAW_ARTIFACTS_BUCKET: raw-artifacts/);
  assert.doesNotMatch(backfillWorkflow, /--limit "\$\{\{ inputs\./);
});
