import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAnnualFinanceTrend,
  parseFinanceYearSlug,
} from "../../apps/web/lib/annual-finance-trend.mjs";

function closure(
  periodStart,
  revenue,
  paid,
  difference,
  status = "operational",
) {
  return {
    periodStart,
    periodEnd: `${periodStart.slice(0, 8)}28`,
    fiscalYear: Number(periodStart.slice(0, 4)),
    closureStatus: status,
    revenueReportAmount: revenue,
    expensePaidAmount: paid,
    operationalDifferenceAmount: difference,
  };
}

test("conserva meses ausentes sem convertê-los em valor zero", () => {
  const result = buildAnnualFinanceTrend(
    [
      closure("2025-01-01", "100.00", "50.00", "50.00"),
      closure("2025-02-01", "80.00", "200.00", "-120.00"),
      closure("2025-03-01", null, null, null, "needs_data"),
    ],
    2025,
  );

  assert.equal(result.state, "available");
  assert.equal(result.comparableMonthCount, 2);
  assert.deepEqual(result.months[0], {
    month: 1,
    periodStart: "2025-01-01",
    closureStatus: "operational",
    revenueAmount: "100.00",
    paidAmount: "50.00",
    operationalDifferenceAmount: "50.00",
    revenueBarBasisPoints: 5000,
    paidBarBasisPoints: 2500,
  });
  assert.deepEqual(result.months[1], {
    month: 2,
    periodStart: "2025-02-01",
    closureStatus: "operational",
    revenueAmount: "80.00",
    paidAmount: "200.00",
    operationalDifferenceAmount: "-120.00",
    revenueBarBasisPoints: 4000,
    paidBarBasisPoints: 10000,
  });
  assert.deepEqual(result.months[2], {
    month: 3,
    periodStart: "2025-03-01",
    closureStatus: "needs_data",
    revenueAmount: null,
    paidAmount: null,
    operationalDifferenceAmount: null,
    revenueBarBasisPoints: null,
    paidBarBasisPoints: null,
  });
  assert.equal(result.months[11].closureStatus, "missing");
  assert.equal(result.months[11].revenueAmount, null);
});

test("falha fechado diante de mês duplicado ou valor inválido", () => {
  assert.deepEqual(
    buildAnnualFinanceTrend(
      [
        closure("2025-01-01", "1.00", "1.00", "0.00"),
        closure("2025-01-01", "2.00", "2.00", "0.00"),
      ],
      2025,
    ),
    { state: "unavailable" },
  );
  assert.deepEqual(
    buildAnnualFinanceTrend(
      [closure("2025-01-01", "1.001", "1.00", "0.00")],
      2025,
    ),
    { state: "unavailable" },
  );
});

test("ignora outros exercícios e rejeita ano fora do contrato", () => {
  const result = buildAnnualFinanceTrend(
    [closure("2024-12-01", "10.00", "9.00", "1.00")],
    2025,
  );
  assert.equal(result.state, "available");
  assert.equal(result.comparableMonthCount, 0);
  assert.equal(result.months.every((month) => month.closureStatus === "missing"), true);
  assert.deepEqual(buildAnnualFinanceTrend([], 2020), { state: "unavailable" });
});

test("aceita somente anos cobertos e nunca interpreta texto parcialmente numérico", () => {
  assert.equal(parseFinanceYearSlug("2025", 2026), 2025);
  assert.equal(parseFinanceYearSlug("2020", 2026), null);
  assert.equal(parseFinanceYearSlug("2027", 2026), null);
  assert.equal(parseFinanceYearSlug("2025abc", 2026), null);
});
