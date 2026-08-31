import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migrationUrl = new URL(
  "../../supabase/migrations/20260831163000_consolidate_source_conflicts_rls.sql",
  import.meta.url,
);

test("source conflict policies are consolidated without broadening worker access", async () => {
  const migration = await readFile(migrationUrl, "utf8");

  for (const policyName of [
    "collector_worker_source_conflicts_select",
    "collector_worker_source_conflicts_insert",
    "collector_worker_expense_report_conflicts_select",
    "collector_worker_expense_report_conflicts_insert",
  ]) {
    assert.match(
      migration,
      new RegExp(`drop policy if exists ${policyName}`),
    );
  }

  assert.equal(
    (migration.match(/create policy collector_worker_source_conflicts_select/g) ?? [])
      .length,
    1,
  );
  assert.equal(
    (migration.match(/create policy collector_worker_source_conflicts_insert/g) ?? [])
      .length,
    1,
  );
  assert.match(migration, /for select to collector_worker/);
  assert.match(migration, /for insert to collector_worker/);

  assert.match(
    migration,
    /target_type = 'finance\.public_obligations'[\s\S]+field_name = 'payments_prior_amount'/,
  );
  assert.match(
    migration,
    /target_type = 'finance\.expense_reports'[\s\S]+field_name ~ '\^budget_unit_subtotal:/,
  );
  assert.match(migration, /status = 'open'/);
  assert.doesNotMatch(migration, /using\s*\(\s*true\s*\)/i);
  assert.doesNotMatch(migration, /with check\s*\(\s*true\s*\)/i);
  assert.doesNotMatch(migration, /\bto\s+(?:anon|authenticated|public)\b/i);
});
