import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260924235122_payroll_declared_month_correction.sql",
    import.meta.url,
  ),
  "utf8",
);

test("sucessor invalidado não substitui a versão anterior da folha", () => {
  // Julho/2026: o PDF de agosto listado também como julho substituiu a versão
  // correta. A correção é append-only e vale em todas as projeções.
  for (const name of [
    "api.get_public_payroll_months(",
    "api.get_public_payroll_months_page(",
    "hr.payroll_month_is_public(",
    "api.get_public_payroll_coverage(",
    "hr.get_pending_payroll_regime_documents(",
    "api.get_public_payroll_regime_breakdown(",
    "hr.get_pending_payroll_compensation_documents(",
    "api.get_public_payroll_compensation_distribution(",
  ]) {
    const start = migration.indexOf(`create or replace function ${name}`);
    assert.ok(start >= 0, `função ausente: ${name}`);
    const body = migration.slice(start, migration.indexOf("$function$;", start));
    assert.match(
      body,
      /and successor\.validation_state <> 'rejected'\s+-- Sucessor invalidado[\s\S]*?where successor_invalidation\.aggregate_id = successor\.id/,
      `regra de sucessor invalidado ausente em ${name}`,
    );
  }
  assert.match(migration, /'declared_month_mismatch'/);
  assert.match(migration, /'mismatched_source_endpoint',/);
  assert.match(migration, /on conflict \(aggregate_id\) do nothing/);
  assert.doesNotMatch(migration, /\bdelete from\b|\bupdate hr\./i);
});
