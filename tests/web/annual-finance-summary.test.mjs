import assert from "node:assert/strict";
import test from "node:test";

import { summarizeAnnualFinances } from "../../apps/web/lib/annual-finance-summary.mjs";

function closure(periodStart, revenue, paid, status = "operational") {
  return {
    periodStart,
    periodEnd: `${periodStart.slice(0, 8)}28`,
    fiscalYear: Number(periodStart.slice(0, 4)),
    closureStatus: status,
    revenueReportAmount: revenue,
    expensePaidAmount: paid,
  };
}

test("soma centavos por ano e informa exatamente os meses incluídos", () => {
  const summaries = summarizeAnnualFinances([
    closure("2026-02-01", "10.01", "8.02"),
    closure("2025-12-01", "20.10", "18.09"),
    closure("2026-01-01", "30.02", "31.03"),
  ]);

  assert.deepEqual(summaries, [
    {
      fiscalYear: 2026,
      comparableMonthCount: 2,
      firstPeriodStart: "2026-01-01",
      lastPeriodStart: "2026-02-01",
      revenueAmount: "40.03",
      paidAmount: "39.05",
      operationalDifferenceAmount: "0.98",
      isFullCalendarYear: false,
    },
    {
      fiscalYear: 2025,
      comparableMonthCount: 1,
      firstPeriodStart: "2025-12-01",
      lastPeriodStart: "2025-12-01",
      revenueAmount: "20.10",
      paidAmount: "18.09",
      operationalDifferenceAmount: "2.01",
      isFullCalendarYear: false,
    },
  ]);
});

test("descarta meses parciais e só reconhece janeiro a dezembro como ano completo", () => {
  const fullYear = Array.from({ length: 12 }, (_, index) =>
    closure(`2025-${String(index + 1).padStart(2, "0")}-01`, "1.00", "0.50"),
  );
  const summaries = summarizeAnnualFinances([
    ...fullYear,
    closure("2026-01-01", null, "2.00", "needs_data"),
  ]);

  assert.equal(summaries.length, 1);
  assert.equal(summaries[0].isFullCalendarYear, true);
  assert.equal(summaries[0].comparableMonthCount, 12);
  assert.equal(summaries[0].revenueAmount, "12.00");
  assert.equal(summaries[0].paidAmount, "6.00");
});

test("falha fechado diante de decimal inválido", () => {
  assert.deepEqual(
    summarizeAnnualFinances([closure("2026-01-01", "1.001", "1.00")]),
    [],
  );
});
