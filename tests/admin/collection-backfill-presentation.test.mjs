import assert from "node:assert/strict";
import test from "node:test";

let formatBackfillProgress;
try {
  ({ formatBackfillProgress } = await import(
    "../../apps/admin/app/collection-backfill.mjs"
  ));
} catch {
  formatBackfillProgress = undefined;
}

test("apresenta a cobertura contínua e a próxima janela do Diário", () => {
  const formatted = formatBackfillProgress?.({
    backfill_horizon: "2021-01-01",
    continuous_coverage_start: "2026-07-24",
    continuous_coverage_end: "2026-08-04",
    next_backfill_start: "2026-07-17",
    next_backfill_end: "2026-07-23",
    backfill_classified_days: 12,
    backfill_total_days: 2042,
    backfill_progress_percent: 0.59,
  });

  assert.deepEqual(formatted, {
    coverage: "24/07/2026 a 04/08/2026",
    nextWindow: "17/07/2026 a 23/07/2026",
    progress: "12 de 2.042 dias contínuos (0,59%)",
    horizon: "01/01/2021",
  });
});

test("não anuncia progresso quando ainda não há cobertura comprovada", () => {
  const formatted = formatBackfillProgress?.({
    backfill_horizon: null,
    continuous_coverage_start: null,
    continuous_coverage_end: null,
    next_backfill_start: null,
    next_backfill_end: null,
    backfill_classified_days: null,
    backfill_total_days: null,
    backfill_progress_percent: null,
  });

  assert.equal(formatted, null);
});
