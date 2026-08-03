import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL(
    "../../.github/workflows/publish-monthly-finance-commentary.yml",
    import.meta.url,
  ),
  "utf8",
);

test("workflow mensal usa cascata, backfill seguro e limite explícito", () => {
  assert.match(workflow, /publish_monthly_finance_commentary/);
  assert.match(workflow, /GROQ_API_KEY/);
  assert.match(workflow, /OPENROUTER_API_KEY/);
  assert.match(workflow, /GEMINI_API_KEY/);
  assert.match(workflow, /--fiscal-year-from/);
  assert.match(workflow, /--fiscal-year-to/);
  assert.match(workflow, /--limit/);
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /timeout-minutes: 15/);
});
