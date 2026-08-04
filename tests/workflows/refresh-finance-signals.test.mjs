import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workflow = await readFile(
  new URL("../../.github/workflows/refresh-finance-signals.yml", import.meta.url),
  "utf8",
);
const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260803124159_finance_deterministic_signals.sql",
    import.meta.url,
  ),
  "utf8",
);

test("workflow de sinais usa identidade técnica e não recebe dados financeiros do shell", () => {
  assert.match(workflow, /QUERIDO_DIARIO_DATABASE_URL/);
  assert.match(workflow, /refresh_finance_signals/);
  assert.match(workflow, /timeout-minutes: 10/);
  assert.doesNotMatch(workflow, /DATABASE_URL=.*\$\{\{ secrets/);
});

test("migration de sinais é versionada, idempotente e neutra", () => {
  assert.match(migration, /finance-duplicate-period/);
  assert.match(migration, /finance-accounting-consistency/);
  assert.match(migration, /on conflict \(slug, version\) do nothing/i);
  assert.match(migration, /não é prova de irregularidade/i);
  assert.match(migration, /get_public_finance_signals/);
  assert.match(migration, /finance-anomaly-rules\/1\.0\.0/);
});
